"""Run orchestration. Each stage is idempotent and recorded in progress['completed'] per round,
so a crashed run resumes where it stopped without paying Apify again (dataset IDs are stored)."""

import asyncio
import copy
import logging
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.apify.client import ApifyAuthError, ApifyCapacityError, ApifyClient, ApifyCreditError, ApifyError
from app.db import SessionLocal
from app.llm.client import LLMError, llm_available
from app.llm.scoring import BATCH_SIZE, heuristic_score, score_batch
from app.logging_setup import log as jlog
from app.logging_setup import redact
from app.models import Job, RawJob, RunStatus, Score, ScrapeTask, SearchRun, SeenJob, Verification
from app.pipeline import dedupe as dd
from app.pipeline import filters as flt
from app.pipeline.prescore import SkillDict, prescore
from app.scrapers.platforms import PLATFORMS, item_id, item_query, map_item
from app.services import apify_keys as keys
from app.services import app_settings
from app.verify.verifier import Verifier

log = logging.getLogger("runner")

STAGES = ["scrape", "normalize", "filter", "dedupe", "prescore", "verify", "score", "finalize"]
STAGE_LABEL = {
    "scrape": "scraping",
    "normalize": "normalizing",
    "filter": "filtering",
    "dedupe": "deduping",
    "prescore": "pre-scoring",
    "verify": "verifying",
    "score": "scoring",
    "finalize": "finalizing",
}
VERIFY_MIN_PRESCORE = 60
MAX_CONCURRENT_APIFY = 10
MAX_402_RETRIES = 60


class Cancelled(Exception):
    pass


@dataclass
class Deps:
    """Pluggable external services, so the demo seed can run the pipeline on recorded fixtures."""

    apify_factory: Callable[[str], Any] = ApifyClient  # called with a token
    verifier_factory: Callable[[], Any] = Verifier
    use_llm: bool | None = None  # None = use the LLM when an API key is configured
    capacity_backoff: tuple[float, float] = (10.0, 30.0)
    use_key_pool: bool = True  # False for the offline demo (no real keys involved)


DEMO_KEY = keys.ResolvedKey(None, "demo fixtures", "demo")


class ApifyPool:
    """Apify clients for one run: today's pooled key for new runs, failover on auth/credit errors,
    and the original key for runs that were already started (their IDs belong to that account)."""

    def __init__(self, ex: "RunExecutor"):
        self.ex = ex
        self.clients: dict[int | None, Any] = {}
        self.current: keys.ResolvedKey | None = None
        self.logged: set[int | None] = set()
        self.lock = asyncio.Lock()

    def _client(self, key: keys.ResolvedKey):
        if key.key_id not in self.clients:
            self.clients[key.key_id] = self.ex.deps.apify_factory(key.token)
        return self.clients[key.key_id]

    def _log_run(self, key: keys.ResolvedKey) -> None:
        if key.key_id not in self.logged:
            self.logged.add(key.key_id)
            keys.log_usage(self.ex.db, key, "run", run_id=self.ex.run_id)
            self.ex.event(f"Using Apify key {key.label} ({key.masked})")

    async def current_key(self) -> keys.ResolvedKey:
        async with self.lock:
            if self.current is None:
                if not self.ex.deps.use_key_pool:
                    self.current = DEMO_KEY
                else:
                    self.current = keys.current_key(self.ex.db)
                    if self.current is None:
                        raise ApifyError("No Apify key available: add keys on the API keys page or set APIFY_TOKEN")
                    self._log_run(self.current)
            return self.current

    async def switch(self, bad: keys.ResolvedKey, reason: str) -> keys.ResolvedKey | None:
        async with self.lock:
            if self.current is not None and self.current.key_id != bad.key_id:
                return self.current  # another task already switched
            nxt = keys.failover(self.ex.db, bad, reason, self.ex.run_id) if self.ex.deps.use_key_pool else None
            self.ex.event(
                f"Apify key {bad.label} failed ({redact(reason)[:160]}); "
                + (f"switching to {nxt.label}" if nxt else "no other key available today")
            )
            self.current = nxt
            if nxt:
                self._log_run(nxt)
            return nxt

    async def start_client(self):
        key = await self.current_key()
        return key, self._client(key)

    def for_task(self, task: ScrapeTask):
        if not self.ex.deps.use_key_pool:
            return self._client(DEMO_KEY)
        key = keys.token_for(self.ex.db, task.apify_key_id)
        if key is None:
            raise ApifyError("the Apify key that started this task was deleted, so its results can't be read")
        return self._client(key)

    async def aclose(self) -> None:
        for c in self.clients.values():
            await c.__aexit__(None, None, None)


def empty_progress() -> dict:
    return {
        "stage": "queued",
        "completed": [],
        "platforms": {},
        "counts": {},
        "per_platform": {},
        "cost": {"apify": {}, "apify_total": 0.0, "llm": 0.0},
        "log": [],
    }


class RunExecutor:
    def __init__(self, run_id: int, deps: Deps | None = None):
        self.run_id = run_id
        self.deps = deps or Deps()
        self.db: Session = SessionLocal()
        self.run: SearchRun = self.db.get(SearchRun, run_id)
        self.p: dict = copy.deepcopy(self.run.progress or {}) or empty_progress()
        for k, v in empty_progress().items():
            self.p.setdefault(k, copy.deepcopy(v))

    # -------------------------------------------------------------- helpers

    def save(self, **changes) -> None:
        self.p.update(changes)
        self.run.progress = copy.deepcopy(self.p)
        flag_modified(self.run, "progress")
        self.run.cost_usd = round(self.p["cost"]["apify_total"] + self.p["cost"]["llm"], 4)
        self.db.commit()

    def event(self, msg: str, **fields) -> None:
        self.p["log"] = (self.p["log"] + [{"ts": datetime.now(UTC).isoformat(timespec="seconds"), "msg": msg}])[-100:]
        jlog(log, logging.INFO, msg, run_id=self.run_id, **fields)
        self.save()

    def set_platform(self, platform: str, **kw) -> None:
        self.p["platforms"].setdefault(platform, {}).update(kw)

    def cancelled(self) -> bool:
        status = self.db.execute(select(SearchRun.status).where(SearchRun.id == self.run_id)).scalar_one()
        return status in (RunStatus.CANCELLING, RunStatus.CANCELLED)

    def check_cancel(self) -> None:
        if self.cancelled():
            raise Cancelled()

    async def should_stop(self) -> bool:
        return self.cancelled()

    async def gather_all(self, coros) -> None:
        """Run coroutines concurrently; let all finish, then surface cancellation or the first error."""
        results = await asyncio.gather(*coros, return_exceptions=True)
        self.check_cancel()
        for r in results:
            if isinstance(r, BaseException) and not isinstance(r, Cancelled):
                raise r

    @property
    def profile(self) -> dict:
        return self.run.resume.parsed_profile or {}

    @property
    def years(self) -> float:
        return float(self.profile.get("total_years_experience") or 0)

    def jobs(self) -> list[Job]:
        return list(self.db.scalars(select(Job).where(Job.run_id == self.run_id)))

    # -------------------------------------------------------------- main

    async def execute(self) -> None:
        run = self.run
        if run.status in (RunStatus.CANCELLED, RunStatus.COMPLETED, RunStatus.DRAFT):
            return
        run.status = RunStatus.RUNNING
        run.started_at = run.started_at or datetime.now(UTC)
        run.error = None
        self.event(f"Run started (round {run.round})")
        try:
            for stage in STAGES:
                key = f"{stage}:{run.round}"
                if key in self.p["completed"]:
                    continue
                self.check_cancel()
                self.save(stage=STAGE_LABEL[stage])
                await getattr(self, f"stage_{stage}")()
                self.p["completed"].append(key)
                self.save()
            run.status = RunStatus.COMPLETED
            run.finished_at = datetime.now(UTC)
            self.event("Run completed")
        except Cancelled:
            await self.abort_apify()
            run.status = RunStatus.CANCELLED
            run.finished_at = datetime.now(UTC)
            self.event("Run cancelled")
        except Exception as exc:  # noqa: BLE001 - record any failure on the run
            log.exception("run failed")
            run.status = RunStatus.FAILED
            run.error = redact(f"{type(exc).__name__}: {exc}")[:2000]
            run.finished_at = datetime.now(UTC)
            self.event(f"Run failed: {run.error}")
        finally:
            self.save(stage=run.status)
            self.db.close()

    async def abort_apify(self) -> None:
        running = [t for t in self.run.tasks if t.apify_run_id and t.status in ("pending", "running")]
        if not running:
            return
        pool = ApifyPool(self)
        try:
            for t in running:
                try:
                    await pool.for_task(t).abort(t.apify_run_id)
                    t.status = "aborted"
                except ApifyError as exc:
                    log.warning(redact(f"abort failed for {t.apify_run_id}: {exc}"))
            self.db.commit()
        finally:
            await pool.aclose()

    # -------------------------------------------------------------- stage: scrape

    async def stage_scrape(self) -> None:
        tasks = [t for t in self.run.tasks if t.round == self.run.round and t.status not in ("fetched", "failed")]
        all_round = [t for t in self.run.tasks if t.round == self.run.round]
        for platform in {t.platform for t in all_round}:
            mine = [t for t in all_round if t.platform == platform]
            self.set_platform(
                platform,
                stage="scraping",
                tasks_total=len(mine),
                tasks_done=sum(t.status in ("fetched", "failed") for t in mine),
            )
        self.save()
        if not tasks:
            return
        existing = set(
            self.db.execute(select(RawJob.platform, RawJob.platform_job_id).where(RawJob.run_id == self.run_id)).all()
        )
        sem = asyncio.Semaphore(MAX_CONCURRENT_APIFY)
        pool = ApifyPool(self)
        try:
            await self.gather_all(self._scrape_task(pool, t, sem, existing) for t in tasks)
        finally:
            await pool.aclose()
        if self.deps.use_key_pool:
            self._record_key_spend()
        failed = [t for t in all_round if t.status == "failed"]
        if failed and len(failed) == len(all_round):
            raise ApifyError(f"all {len(failed)} scrape tasks failed; first error: {failed[0].error}")
        for platform in {t.platform for t in all_round}:
            self.set_platform(platform, stage="scraped")
        self.save()

    async def _scrape_task(self, pool: ApifyPool, task: ScrapeTask, sem: asyncio.Semaphore, existing: set) -> None:
        async with sem:
            try:
                if not task.apify_run_id:
                    for attempt in range(MAX_402_RETRIES):
                        self.check_cancel()
                        key, apify = await pool.start_client()
                        try:
                            data = await apify.start(task.actor_id, task.input, task.memory_mb, task.max_charge_usd)
                            task.apify_key_id = key.key_id
                            break
                        except (ApifyAuthError, ApifyCreditError) as exc:
                            if await pool.switch(key, str(exc)) is None:
                                raise ApifyError(f"no usable Apify key left today ({exc})") from None
                        except ApifyCapacityError:
                            wait = random.uniform(*self.deps.capacity_backoff)
                            self.event(
                                f"{task.platform}: Apify capacity limit (402), retrying in {wait:.0f}s",
                                attempt=attempt + 1,
                            )
                            await asyncio.sleep(wait)
                    else:
                        raise ApifyError("Apify capacity limit persisted; giving up on this task")
                    task.apify_run_id = data["id"]
                    task.dataset_id = data.get("defaultDatasetId")
                    task.status = "running"
                    self.db.commit()

                apify = pool.for_task(task)
                if task.status == "running":
                    data = await apify.wait(task.apify_run_id, should_stop=self.should_stop)
                    task.dataset_id = data.get("defaultDatasetId") or task.dataset_id
                    task.cost_usd = float(data.get("usageTotalUsd") or 0.0)
                    status = data.get("status")
                    if status == "ABORTED" and self.cancelled():
                        task.status = "aborted"
                        self.db.commit()
                        return
                    # Even FAILED / TIMED-OUT / max-charge-ABORTED runs may have stored partial results.
                    task.status = "succeeded" if status == "SUCCEEDED" else "partial"
                    if status != "SUCCEEDED":
                        task.error = f"Apify run ended with status {status}"
                    self.db.commit()

                items = await apify.items(task.dataset_id) if task.dataset_id else []
                added = self._store_items(task, items, existing)
                task.item_count = len(items)
                task.status = "fetched"
                self.db.commit()
                self.event(f"{task.platform}: {len(items)} items ({added} new) from {task.actor_id}", task_id=task.id)
            except Cancelled:
                raise
            except Exception as exc:  # noqa: BLE001 - one failed task must not kill the run
                task.status = "failed"
                task.error = redact(f"{type(exc).__name__}: {exc}")[:1000]
                self.db.commit()
                self.event(f"{task.platform}: task {task.id} failed: {task.error}")
            finally:
                self._add_cost()
                pl = self.p["platforms"].setdefault(task.platform, {})
                pl["tasks_done"] = sum(
                    t.status in ("fetched", "failed")
                    for t in self.run.tasks
                    if t.platform == task.platform and t.round == self.run.round
                )
                pl["items"] = sum(t.item_count for t in self.run.tasks if t.platform == task.platform)
                self.save()

    def _record_key_spend(self) -> None:
        """Write how many Apify runs, items and dollars this run used on each key into the usage log."""
        per_key: dict[int | None, list[ScrapeTask]] = {}
        for t in self.run.tasks:
            if t.apify_run_id:
                per_key.setdefault(t.apify_key_id, []).append(t)
        for key_id, ts in per_key.items():
            keys.record_run_spend(
                self.db,
                self.run_id,
                key_id,
                len(ts),
                sum(t.cost_usd or 0 for t in ts),
                sum(t.item_count or 0 for t in ts),
            )

    def _add_cost(self) -> None:
        per: dict = {}
        for t in self.run.tasks:
            per[t.platform] = round(per.get(t.platform, 0.0) + (t.cost_usd or 0.0), 4)
        self.p["cost"]["apify"] = per
        self.p["cost"]["apify_total"] = round(sum(per.values()), 4)

    def _store_items(self, task: ScrapeTask, items: list[dict], existing: set) -> int:
        added = 0
        for item in items:
            pid = item_id(task.platform, item)
            if not pid or (task.platform, pid) in existing:
                continue
            q = item_query(item, task.query_meta or {})
            self.db.add(
                RawJob(
                    run_id=self.run_id,
                    platform=task.platform,
                    platform_job_id=pid,
                    payload=item,
                    keyword=q.get("keyword"),
                    location_query=q.get("location"),
                    is_remote_query=bool(q.get("remote")),
                )
            )
            existing.add((task.platform, pid))
            added += 1
        self.db.commit()
        return added

    # -------------------------------------------------------------- stage: normalize

    async def stage_normalize(self) -> None:
        blocklist = app_settings.get_setting(self.db, "agency_blocklist") or []
        allowlist = app_settings.get_setting(self.db, "agency_allowlist") or []
        raws = list(self.db.scalars(select(RawJob).where(RawJob.run_id == self.run_id, RawJob.normalized.is_(False))))
        for platform in PLATFORMS:
            if platform in self.p["platforms"]:
                self.set_platform(platform, stage="normalizing")
        self.save()
        for raw in raws:
            try:
                f = map_item(raw.platform, raw.payload, raw.is_remote_query)
            except Exception as exc:  # noqa: BLE001 - skip malformed items, keep the run going
                log.warning(f"could not normalize raw job {raw.id}: {exc}")
                raw.normalized = True
                continue
            city = flt.resolve_city(
                f["cities"], f["is_remote"], self.run.locations or [], self.run.include_remote_india
            )
            self.db.add(
                Job(
                    run_id=self.run_id,
                    raw_job_id=raw.id,
                    platform=raw.platform,
                    platform_job_id=raw.platform_job_id,
                    title=f["title"][:500],
                    company=(f["company"] or "")[:300],
                    location_text=(f["location_text"] or "")[:500],
                    city=city,
                    is_remote=f["is_remote"],
                    work_mode=f["work_mode"],
                    posted_date=f["posted_date"],
                    description=f["description"],
                    exp_min=f["exp_min"],
                    exp_max=f["exp_max"],
                    salary_text=(f["salary_text"] or None) and f["salary_text"][:200],
                    listing_url=f["listing_url"],
                    apply_url=f["apply_url"],
                    employer_url=f["employer_url"],
                    applicants_text=f["applicants_text"],
                    is_agency=flt.is_agency(f["company"], f["agency_signal"], blocklist, allowlist),
                    dedupe_key=dd.dedupe_key(f["company"], f["title"]),
                    prescore_detail={"extra": f.get("extra", {})},
                )
            )
            raw.normalized = True
        self.db.commit()
        collected = sum(t.item_count for t in self.run.tasks)
        unique = len(self.jobs())
        self.p["counts"].update(collected=collected, unique=unique)
        per = Counter(j.platform for j in self.jobs())
        for platform in PLATFORMS:
            pp = self.p["per_platform"].setdefault(platform, {})
            pp["collected"] = sum(t.item_count for t in self.run.tasks if t.platform == platform)
            pp["unique"] = per.get(platform, 0)
        self.event(f"Normalized {len(raws)} new listings ({unique} unique so far)")

    # -------------------------------------------------------------- stage: filter

    async def stage_filter(self) -> None:
        s = lambda k: app_settings.get_setting(self.db, k)  # noqa: E731
        cfg = flt.FilterConfig(
            cities=self.run.locations or [],
            include_remote=self.run.include_remote_india,
            work_arrangement=self.run.work_arrangement or "any",
            candidate_years=self.years,
            agency_blocklist=s("agency_blocklist") or [],
            title_exclusions=s("title_exclusions") or [],
            seniority_exclusions=s("seniority_exclusions") or [],
            allow_senior_max_years=s("allow_senior_max_years"),
        )
        # Jobs shown in an earlier run's ranked list, or marked by the user, are skipped (by platform job ID).
        seen = {
            (pl, pid)
            for pl, pid, first_run in self.db.execute(
                select(SeenJob.platform, SeenJob.platform_job_id, SeenJob.first_run_id)
            ).all()
            if first_run != self.run_id
        }
        excluded = [c.strip().lower() for c in (self.run.exclude_companies or []) if c.strip()]
        reasons: Counter = Counter()
        per_pass: Counter = Counter()
        for job in self.jobs():
            company = (job.company or "").lower()
            if (job.platform, job.platform_job_id) in seen:
                job.filter_reason = "seen_before"
            elif any(x in company for x in excluded):
                job.filter_reason = "excluded_company"
            else:
                job.filter_reason = flt.check(job, cfg)
            if job.filter_reason:
                reasons[job.filter_reason] += 1
            else:
                per_pass[job.platform] += 1
        self.db.commit()
        passed = sum(per_pass.values())
        self.p["counts"].update(filtered=dict(reasons), passed_filters=passed)
        for platform in PLATFORMS:
            self.p["per_platform"].setdefault(platform, {})["passed_filters"] = per_pass.get(platform, 0)
        self.event(f"Filters: {passed} passed, {sum(reasons.values())} removed", reasons=dict(reasons))

    # -------------------------------------------------------------- stage: dedupe

    def _verified_map(self) -> dict[int, str]:
        rows = self.db.execute(
            select(Verification.job_id, Verification.status).join(Job).where(Job.run_id == self.run_id)
        ).all()
        return dict(rows)

    async def stage_dedupe(self) -> None:
        self._dedupe()

    def _dedupe(self) -> None:
        jobs = self.jobs()
        for j in jobs:
            j.duplicate_of = None
            j.alt_sources = []
        passing = [j for j in jobs if not j.filter_reason]
        clusters = dd.find_duplicates(passing, self._verified_map())
        merged = 0
        for primary_id, dups in clusters.items():
            primary = self.db.get(Job, primary_id)
            primary.alt_sources = [{"platform": d.platform, "url": d.listing_url, "job_id": d.id} for d in dups]
            for d in dups:
                d.duplicate_of = primary_id
                merged += 1
        self.db.commit()
        after = len(passing) - merged
        self.p["counts"].update(duplicates_merged=merged, after_dedupe=after)
        self.event(f"Dedupe: merged {merged} cross-listed duplicates; {after} unique jobs remain")

    # -------------------------------------------------------------- stage: prescore

    async def stage_prescore(self) -> None:
        skills = SkillDict.from_profile(self.profile)
        roles = self.run.roles or []
        n_ok = 0
        for job in self.jobs():
            if job.filter_reason:
                continue
            total, detail = prescore(job, skills, roles, self.years, self.run.locations or [])
            job.prescore = total
            job.prescore_detail = {**(job.prescore_detail or {}), **detail}
            if job.duplicate_of is None and total >= VERIFY_MIN_PRESCORE:
                n_ok += 1
        self.db.commit()
        self.p["counts"]["prescore_ge_60"] = n_ok
        self.event(f"Pre-score: {n_ok} unique jobs scored {VERIFY_MIN_PRESCORE}+ and go to verification")

    # -------------------------------------------------------------- stage: verify

    def _verify_candidates(self, include_dups: bool = False) -> list[Job]:
        verified = self._verified_map()
        jobs = [j for j in self.jobs() if not j.filter_reason and (j.prescore or 0) >= VERIFY_MIN_PRESCORE]
        if not include_dups:
            return sorted(
                [j for j in jobs if j.duplicate_of is None and j.id not in verified], key=lambda j: -(j.prescore or 0)
            )
        # Second pass: duplicates whose primary could not be verified active.
        return [
            j
            for j in jobs
            if j.duplicate_of is not None and j.id not in verified and verified.get(j.duplicate_of) != "verified_active"
        ]

    async def stage_verify(self) -> None:
        verifier = self.deps.verifier_factory()
        try:
            for pass_no in (1, 2):
                cands = self._verify_candidates(include_dups=pass_no == 2)
                if not cands:
                    continue
                if pass_no == 1:
                    self.event(f"Verifying {len(cands)} jobs")
                else:
                    self.event(f"Verifying {len(cands)} alternate sources for unverified jobs")
                by_platform: dict[str, list[Job]] = {}
                for j in cands:
                    by_platform.setdefault(j.platform, []).append(j)
                for platform, js in by_platform.items():
                    self.set_platform(platform, stage="verifying", verify_total=len(js), verify_done=0)
                self.save()
                await self.gather_all(self._verify_platform(verifier, p, js) for p, js in by_platform.items())
                for platform in by_platform:
                    self.set_platform(platform, stage="verified")
                if pass_no == 2:
                    self._dedupe()  # re-pick primaries now that duplicates may be verified active
        finally:
            await verifier.aclose()
        self._verification_counts()
        self.save()

    async def _verify_platform(self, verifier, platform: str, jobs: list[Job]) -> None:
        sem = asyncio.Semaphore(3 if platform == "indeed" else 1)

        async def one(job: Job):
            async with sem:
                self.check_cancel()
                if platform == "linkedin":
                    res = await verifier.linkedin(job.platform_job_id)
                elif platform == "naukri":
                    res = await verifier.naukri(job.listing_url)
                else:
                    extra = (job.prescore_detail or {}).get("extra", {})
                    res = await verifier.indeed(bool(extra.get("expired")), job.employer_url)
                self.db.merge(
                    Verification(
                        job_id=job.id,
                        status=res["status"],
                        method=res["method"],
                        easy_apply=res.get("easy_apply"),
                        evidence=res["evidence"],
                        checked_at=datetime.now(UTC),
                    )
                )
                ev = res["evidence"]
                if ev.get("applicants") and not job.applicants_text:
                    job.applicants_text = ev["applicants"][:100]
                self.db.commit()
                pl = self.p["platforms"].setdefault(platform, {})
                pl["verify_done"] = pl.get("verify_done", 0) + 1
                self.save()

        await self.gather_all(one(j) for j in jobs)

    def _verification_counts(self) -> None:
        rows = self.db.execute(
            select(Verification.status, Verification.easy_apply, Job.platform, Job.duplicate_of)
            .join(Job)
            .where(Job.run_id == self.run_id)
        ).all()
        c: Counter = Counter()
        per: dict[str, Counter] = {}
        for status, easy, platform, dup in rows:
            if dup is not None:
                continue
            if status == "verified_active" and easy and self.run.exclude_linkedin_easy_apply:
                c["easy_apply_excluded"] += 1
                per.setdefault(platform, Counter())["easy_apply_excluded"] += 1
            else:
                c[status] += 1
                per.setdefault(platform, Counter())[status] += 1
        self.p["counts"]["verified"] = {
            k: c.get(k, 0) for k in ("verified_active", "uncertain", "inactive", "easy_apply_excluded")
        }
        for platform in PLATFORMS:
            self.p["per_platform"].setdefault(platform, {})["verified"] = dict(per.get(platform, {}))

    # -------------------------------------------------------------- stage: score

    def _score_candidates(self) -> list[Job]:
        q = (
            select(Job)
            .join(Verification)
            .where(
                Job.run_id == self.run_id,
                Job.filter_reason.is_(None),
                Job.duplicate_of.is_(None),
                Verification.status == "verified_active",
            )
        )
        jobs = [
            j for j in self.db.scalars(q) if not (self.run.exclude_linkedin_easy_apply and j.verification.easy_apply)
        ]
        return sorted(jobs, key=lambda j: -(j.prescore or 0))

    async def stage_score(self) -> None:
        top_n = int(app_settings.get_setting(self.db, "llm_top_n") or 150)
        cands = self._score_candidates()[:top_n]
        todo = [j for j in cands if j.score is None]
        use_llm = self.deps.use_llm if self.deps.use_llm is not None else llm_available()
        model = app_settings.llm_model(self.db) if use_llm else "heuristic"
        if not todo:
            self._score_counts()
            return
        self.event(f"Scoring {len(todo)} jobs with {model}" + ("" if use_llm else " (no ANTHROPIC_API_KEY)"))
        self.p["scoring"] = {"total": len(todo), "done": 0, "failed": 0}
        self.save()

        if not use_llm:
            for job in todo:
                self._save_score(job, heuristic_score(job, self.profile), "heuristic")
            self.p["scoring"]["done"] = len(todo)
        else:
            batches = [todo[i : i + BATCH_SIZE] for i in range(0, len(todo), BATCH_SIZE)]
            sem = asyncio.Semaphore(3)

            async def run_batch(batch: list[Job]):
                async with sem:
                    self.check_cancel()
                    try:
                        items, cost = await score_batch(batch, self.profile, model)
                    except LLMError as exc:
                        self.p["scoring"]["failed"] += len(batch)
                        self.event(f"Scoring batch failed after retry: {redact(exc)[:300]}")
                        return
                    self.p["cost"]["llm"] = round(self.p["cost"]["llm"] + cost, 5)
                    by_id = {j.id: j for j in batch}
                    for item in items:
                        self._save_score(by_id[item.job_id], item, model)
                    self.p["scoring"]["done"] += len(batch)
                    self.save()

            await self.gather_all(run_batch(b) for b in batches)
        self.db.commit()
        self._score_counts()
        self.save()

    def _save_score(self, job: Job, item, model: str) -> None:
        self.db.merge(
            Score(
                job_id=job.id,
                total=item.total,
                breakdown=item.breakdown,
                company_tier=item.company_tier,
                experience_summary=item.experience_summary,
                key_skills_match=item.key_skills_match,
                why_fits=item.why_fits,
                notes=item.notes,
                category=item.category,
                model=model,
                created_at=datetime.now(UTC),
            )
        )
        self.db.commit()

    def _score_counts(self) -> None:
        scores = list(self.db.scalars(select(Score).join(Job).where(Job.run_id == self.run_id)))
        self.p["counts"]["scored"] = len(scores)
        self.p["counts"]["below_min_score"] = sum(s.total < self.run.min_score for s in scores)

    # -------------------------------------------------------------- stage: finalize

    async def stage_finalize(self) -> None:
        final = final_jobs_query(self.db, self.run)
        n = len(final)
        self.p["counts"]["final"] = n
        per = Counter(j.platform for j in final)
        for platform in PLATFORMS:
            self.p["per_platform"].setdefault(platform, {})["final"] = per.get(platform, 0)
            if platform in self.p["platforms"]:
                self.set_platform(platform, stage="done")
        self.p["target_met"] = n >= self.run.target_count
        recorded = self._record_seen(final)
        self.event(
            f"{n} ranked jobs (target {self.run.target_count}); {recorded} new job IDs added to the "
            "seen history so later runs skip them"
        )

    def _record_seen(self, final: list[Job]) -> int:
        """Remember shown jobs (and their cross-listings on other platforms) by platform job ID."""
        ids = [j.id for j in final]
        dup_rows = self.db.scalars(select(Job).where(Job.duplicate_of.in_(ids))).all() if ids else []
        existing = set(self.db.execute(select(SeenJob.platform, SeenJob.platform_job_id)).all())
        added = 0
        for j in [*final, *dup_rows]:
            if (j.platform, j.platform_job_id) in existing:
                continue
            existing.add((j.platform, j.platform_job_id))
            self.db.add(
                SeenJob(
                    platform=j.platform,
                    platform_job_id=j.platform_job_id,
                    title=j.title[:500],
                    company=(j.company or "")[:300],
                    first_run_id=self.run_id,
                    reason="shown",
                )
            )
            added += 1
        self.db.commit()
        return added


def final_jobs_query(db: Session, run: SearchRun) -> list[Job]:
    """Jobs that appear in the ranked list and the export: verified active, scored >= min_score."""
    q = (
        select(Job)
        .join(Verification)
        .join(Score)
        .where(
            Job.run_id == run.id,
            Job.filter_reason.is_(None),
            Job.duplicate_of.is_(None),
            Verification.status == "verified_active",
            Score.total >= run.min_score,
        )
        .order_by(Score.total.desc())
    )
    return [j for j in db.scalars(q) if not (run.exclude_linkedin_easy_apply and j.verification.easy_apply)]


def demo_deps() -> Deps:
    from app.demo import FixtureApify, FixtureVerifier

    return Deps(apify_factory=FixtureApify, verifier_factory=FixtureVerifier, use_llm=False, use_key_pool=False)


async def execute_run(run_id: int, deps: Deps | None = None) -> None:
    if deps is None:
        with SessionLocal() as db:
            run = db.get(SearchRun, run_id)
            if run and (run.estimate or {}).get("demo"):
                deps = demo_deps()  # demo runs (and their expansions) never touch Apify or live sites
    await RunExecutor(run_id, deps).execute()
