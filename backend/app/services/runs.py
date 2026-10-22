"""Run lifecycle: estimate, start, expand, cancel."""

import logging

from sqlalchemy.orm import Session

from app.apify.client import ApifyClient, ApifyError, summarize_limits
from app.config import get_settings
from app.logging_setup import redact
from app.models import RunStatus, ScrapeTask, SearchRun
from app.pipeline.estimate import estimate, plan_tasks
from app.pipeline.runner import empty_progress
from app.scrapers.keywords import flatten, synonym_keywords
from app.scrapers.platforms import PRICE_PER_ITEM, TaskSpec
from app.services import apify_keys as keys
from app.services import app_settings

log = logging.getLogger("runs")

EXPAND_STEPS = ["synonyms", "window_14", "page_further"]
EXPAND_LABEL = {
    "synonyms": "Add synonym keywords",
    "window_14": "Extend the date window to 14 days",
    "page_further": "Fetch more results per search (page further)",
}


class RunError(Exception):
    pass


async def remaining_credit(db: Session) -> tuple[keys.ResolvedKey | None, float | None, str | None]:
    """Today's key and its remaining monthly credit in USD (None if unknown). Never fails over."""
    key = keys.current_key(db)
    if key is None:
        return None, None, "no Apify key configured (add keys on the API keys page or set APIFY_TOKEN)"
    try:
        async with ApifyClient(key.token) as client:
            return key, summarize_limits(await client.limits())["remaining_usd"], None
    except (ApifyError, Exception) as exc:  # noqa: BLE001 - network or auth problems
        return key, None, redact(exc)


def _estimate(db: Session, run: SearchRun, specs: list[TaskSpec], credit: float | None) -> dict:
    return estimate(
        specs, app_settings.llm_model(db), int(app_settings.get_setting(db, "llm_top_n") or 150),
        cap=get_settings().max_run_cost_usd, spent=sum(t.cost_usd or 0 for t in run.tasks),
        remaining_credit=credit,
    )


def _key_note(est: dict, key: keys.ResolvedKey | None, err: str | None) -> dict:
    if key is not None:
        est["apify_key"] = {"label": key.label, "masked": key.masked}
    if err:
        est["credit_check"] = f"Monthly credit not checked: {err}"
    return est


async def estimate_specs(db: Session, run: SearchRun, specs: list[TaskSpec], check_credit: bool = True) -> dict:
    """Cost estimate for a preview. Uses today's key's credit but never switches keys."""
    key, credit, err = (await remaining_credit(db)) if check_credit else (None, None, None)
    return _key_note(_estimate(db, run, specs, credit), key, err)


async def estimate_for_start(db: Session, run: SearchRun, specs: list[TaskSpec]) -> dict:
    """Estimate before paying: if today's key can't cover the Apify estimate, fail over to the next key."""
    needed = _estimate(db, run, specs, None)["apify_total_usd"]
    key, credit, err = await keys.key_with_credit(db, needed, run_id=run.id)
    est = _key_note(_estimate(db, run, specs, credit), key, err)
    if key is None:
        est["ok"] = False
        est["reasons"] = [*est.get("reasons", []), err or "no usable Apify key"]
    return est


def create_tasks(db: Session, run: SearchRun, specs: list[TaskSpec], round_no: int) -> None:
    """Persist ScrapeTasks with a per-run maxTotalChargeUsd that never exceeds the remaining run cap."""
    budget = max(get_settings().max_run_cost_usd - sum(t.cost_usd or 0 for t in run.tasks), 0.0)
    total_est = sum(s.est_cost for s in specs) or 1.0
    for s in specs:
        # Headroom over the estimate for start events, capped to this task's share of the remaining budget.
        share = budget * (s.est_cost / total_est)
        max_charge = max(min(s.est_cost * 1.15 + 0.02, share), PRICE_PER_ITEM[s.platform] * 10)
        db.add(ScrapeTask(run_id=run.id, round=round_no, platform=s.platform, actor_id=s.actor_id, input=s.input,
                          query_meta=s.query_meta, memory_mb=s.memory_mb, max_charge_usd=round(max_charge, 4),
                          est_items=s.est_items))
    db.commit()


async def start_run(db: Session, run: SearchRun) -> dict:
    if run.status not in (RunStatus.DRAFT, RunStatus.FAILED):
        raise RunError(f"run is {run.status}")
    if not keys.has_any_token(db):
        raise RunError("No Apify key configured: add keys on the API keys page, or set APIFY_TOKEN in .env "
                       "(or load the demo seed instead)")
    if not run.resume.parsed_profile:
        raise RunError("resume has no parsed profile")
    if run.status == RunStatus.DRAFT:
        specs = plan_tasks(run)
        if not specs:
            raise RunError("nothing to scrape: choose at least one platform, keyword and location")
        est = await estimate_for_start(db, run, specs)
        run.estimate = est
        if not est["ok"]:
            db.commit()
            raise RunError(" ".join(est["reasons"]))
        create_tasks(db, run, specs, run.round)
        run.progress = empty_progress()
    run.status = RunStatus.QUEUED
    run.error = None
    db.commit()
    return run.estimate or {}


def next_expand_step(run: SearchRun) -> str | None:
    for step in EXPAND_STEPS:
        if step in (run.expand_steps or []):
            continue
        if step == "window_14" and run.posted_within_days >= 14:
            continue
        if step == "synonyms" and not synonym_keywords(run.keywords or {}):
            continue
        return step
    return None


def expansion_specs(run: SearchRun, step: str) -> tuple[list[TaskSpec], dict]:
    depth = 2 if "page_further" in (run.expand_steps or []) or step == "page_further" else 1
    if step == "synonyms":
        extra = synonym_keywords(run.keywords or {})
        return plan_tasks(run, keywords=flatten(extra), depth=depth), {"keywords_added": extra}
    if step == "window_14":
        return plan_tasks(run, window_days=14, depth=depth), {"posted_within_days": 14}
    if step == "page_further":
        return plan_tasks(run, depth=2), {"depth": 2}
    raise RunError(f"unknown expand step {step}")


async def expand_run(db: Session, run: SearchRun, confirm: bool) -> dict:
    if run.status != RunStatus.COMPLETED:
        raise RunError("only completed runs can be expanded")
    step = next_expand_step(run)
    if step is None:
        raise RunError("no further expansion steps are available")
    specs, changes = expansion_specs(run, step)
    demo = bool((run.estimate or {}).get("demo"))
    est = await estimate_specs(db, run, specs, check_credit=not demo)
    if demo:
        est |= {"demo": True, "note": "Demo run: replays recorded fixtures, no Apify credit is spent."}
    out = {"step": step, "label": EXPAND_LABEL[step], "changes": changes, "estimate": est,
           "min_score_unchanged": run.min_score}
    if not confirm:
        return out
    if not demo:
        est = out["estimate"] = await estimate_for_start(db, run, specs)
    if not est["ok"]:
        raise RunError(" ".join(est["reasons"]))
    if step == "synonyms":
        merged = {k: list(v) for k, v in (run.keywords or {}).items()}
        for cat, kws in changes["keywords_added"].items():
            merged.setdefault(cat, []).extend(kws)
        run.keywords = merged
    if step == "window_14":
        run.posted_within_days = 14
    run.round += 1
    run.expand_steps = list(run.expand_steps or []) + [step]
    create_tasks(db, run, specs, run.round)
    run.status = RunStatus.QUEUED
    run.finished_at = None
    db.commit()
    out["started"] = True
    return out


async def cancel_run(db: Session, run: SearchRun) -> None:
    if run.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
        return
    was_draft = run.status == RunStatus.DRAFT
    run.status = RunStatus.CANCELLED if was_draft else RunStatus.CANCELLING
    db.commit()
    running = [t for t in run.tasks if t.apify_run_id and t.status in ("pending", "running")]
    if running and not (run.estimate or {}).get("demo"):
        for t in running:  # abort with the key that started each run (IDs are per account)
            key = keys.token_for(db, t.apify_key_id)
            if key is None:
                continue
            try:
                async with ApifyClient(key.token) as client:
                    await client.abort(t.apify_run_id)
                t.status = "aborted"
            except ApifyError as exc:
                log.warning(redact(f"abort {t.apify_run_id} failed: {exc}"))
    db.commit()
