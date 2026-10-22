import asyncio
import json
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.serializers import job_detail, job_row, resume_out, run_out
from app.apify.client import ApifyClient, ApifyError, summarize_limits
from app.config import ALLOWED_MODELS, get_settings
from app.db import SessionLocal, get_db
from app.export.excel import FILENAME, build_workbook
from app.llm.client import LLMError, llm_available
from app.logging_setup import redact
from app.models import Job, Resume, RunStatus, Score, SearchRun, Verification
from app.pipeline.estimate import plan_tasks
from app.pipeline.runner import final_jobs_query
from app.pipeline.text import CITIES
from app.resume.analyze import Profile, analyze_resume
from app.resume.extract import UnsupportedResume, extract_text
from app.scrapers.keywords import ROLE_CATEGORIES, generate_keywords
from app.scrapers.platforms import PLATFORMS
from app.services import apify_keys, app_settings
from app.services.runs import RunError, cancel_run, estimate_specs, expand_run, start_run
from app.worker import enqueue_run

router = APIRouter()

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _get(db: Session, model, id_: int):
    obj = db.get(model, id_)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} {id_} not found")
    return obj


@router.get("/health")
def health():
    return {"ok": True, "time": datetime.now(UTC).isoformat()}


@router.get("/meta")
def meta(db: Session = Depends(get_db)):
    return {"roles": ROLE_CATEGORIES, "cities": CITIES, "platforms": PLATFORMS,
            "llm_configured": llm_available(), "apify_configured": apify_keys.has_any_token(db),
            "max_run_cost_usd": get_settings().max_run_cost_usd}


# ------------------------------------------------------------------ resumes


@router.post("/resumes")
async def upload_resumes(files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    if not files:
        raise HTTPException(400, "upload at least one resume")
    texts, names = [], []
    for i, f in enumerate(files, start=1):
        data = await f.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"{f.filename} is larger than 10 MB")
        try:
            text = extract_text(f.filename or "resume", data)
        except UnsupportedResume as exc:
            raise HTTPException(400, str(exc)) from None
        except Exception as exc:  # noqa: BLE001 - corrupt files
            raise HTTPException(400, f"could not read {f.filename}: {exc}") from None
        if len(text) < 100:
            raise HTTPException(400, f"{f.filename}: no readable text (scanned PDF?)")
        names.append(f.filename or f"resume{i}")
        texts.append(f"=== RESUME {i}: {f.filename} ===\n{text}")
    raw = "\n\n".join(texts)
    try:
        profile, cost = await analyze_resume(raw, app_settings.llm_model(db))
    except LLMError as exc:
        raise HTTPException(502, f"resume analysis failed: {redact(exc)}") from None
    resume = Resume(filename=" + ".join(names), raw_text=raw, parsed_profile=profile)
    db.add(resume)
    db.commit()
    return resume_out(resume) | {"llm_cost_usd": round(cost, 4)}


@router.get("/resumes")
def list_resumes(db: Session = Depends(get_db)):
    return [resume_out(r) for r in db.scalars(select(Resume).order_by(Resume.id.desc()).limit(50))]


@router.get("/resumes/{resume_id}")
def get_resume(resume_id: int, db: Session = Depends(get_db)):
    return resume_out(_get(db, Resume, resume_id))


@router.put("/resumes/{resume_id}/profile")
def update_profile(resume_id: int, profile: Profile, db: Session = Depends(get_db)):
    resume = _get(db, Resume, resume_id)
    source = (resume.parsed_profile or {}).get("source")
    resume.parsed_profile = profile.model_dump() | {"source": source, "edited": True}
    db.commit()
    return resume_out(resume)


# ------------------------------------------------------------------ settings


@router.get("/settings/apify")
async def apify_status(db: Session = Depends(get_db)):
    """Connection status and credit for today's Apify key (pooled key, or APIFY_TOKEN). Never the token."""
    key = apify_keys.current_key(db)
    if key is None:
        return {"configured": False, "connected": False}
    try:
        async with ApifyClient(key.token) as client:
            me = await client.me()
            limits = summarize_limits(await client.limits())
    except ApifyError as exc:
        return {"configured": True, "connected": False, "error": redact(exc)}
    except Exception as exc:  # noqa: BLE001 - network failures
        return {"configured": True, "connected": False, "error": redact(f"{type(exc).__name__}: {exc}")}
    plan = me.get("plan") or {}
    return {"configured": True, "connected": True, "username": me.get("username"),
            "plan": plan.get("id") if isinstance(plan, dict) else plan, "key_label": key.label,
            "key_masked": key.masked, **limits}


@router.get("/settings")
def get_app_settings(db: Session = Depends(get_db)):
    return app_settings.all_settings(db) | {"llm_configured": llm_available(),
                                            "max_run_cost_usd": get_settings().max_run_cost_usd,
                                            "respect_robots_txt": get_settings().respect_robots_txt}


class SettingsIn(BaseModel):
    agency_blocklist: list[str] | None = None
    agency_allowlist: list[str] | None = None
    title_exclusions: list[str] | None = None
    seniority_exclusions: list[str] | None = None
    allow_senior_max_years: float | None = None
    llm_model: Literal[tuple(ALLOWED_MODELS)] | None = None  # type: ignore[valid-type]
    llm_top_n: int | None = Field(default=None, ge=5, le=500)


@router.put("/settings")
def put_app_settings(body: SettingsIn, db: Session = Depends(get_db)):
    values = body.model_dump(exclude_unset=True)
    return app_settings.update_settings(db, values) | {"llm_configured": llm_available()}


# ------------------------------------------------------------------ runs


class KeywordsIn(BaseModel):
    resume_id: int
    roles: list[str]


@router.post("/keywords/suggest")
def suggest_keywords(body: KeywordsIn, db: Session = Depends(get_db)):
    resume = _get(db, Resume, body.resume_id)
    return {"keywords": generate_keywords(body.roles, resume.parsed_profile)}


class RunIn(BaseModel):
    resume_id: int
    roles: list[str] = Field(min_length=1)
    locations: list[str] = []
    include_remote_india: bool = True
    work_arrangement: Literal["any", "remote_only", "office_or_hybrid"] = "any"
    posted_within_days: Literal[7, 14] = 7
    platforms: list[Literal["linkedin", "naukri", "indeed"]] = Field(default_factory=lambda: list(PLATFORMS))
    exclude_linkedin_easy_apply: bool = True
    target_count: int = Field(default=60, ge=1, le=1000)
    min_score: int = Field(default=65, ge=0, le=100)
    keywords: dict[str, list[str]] | None = None
    exclude_companies: list[str] = Field(default_factory=list, max_length=500)


def _validate_run(body: RunIn) -> None:
    bad = [c for c in body.locations if c not in CITIES]
    if bad:
        raise HTTPException(400, f"unknown locations {bad}; choose from {CITIES}")
    if not body.locations and not body.include_remote_india:
        raise HTTPException(400, "choose at least one city or enable Remote (India)")
    if not body.platforms:
        raise HTTPException(400, "choose at least one platform")


@router.post("/runs")
async def create_run(body: RunIn, db: Session = Depends(get_db)):
    _validate_run(body)
    resume = _get(db, Resume, body.resume_id)
    data = body.model_dump()
    if not data.get("keywords"):
        data["keywords"] = generate_keywords(body.roles, resume.parsed_profile)
    data["keywords"] = {k: [kw.strip() for kw in v if kw.strip()] for k, v in data["keywords"].items()}
    run = SearchRun(**data, status=RunStatus.DRAFT, progress={})
    db.add(run)
    db.commit()
    run.estimate = await estimate_specs(db, run, plan_tasks(run))
    db.commit()
    return run_out(run)


@router.patch("/runs/{run_id}")
async def update_run(run_id: int, body: RunIn, db: Session = Depends(get_db)):
    run = _get(db, SearchRun, run_id)
    if run.status != RunStatus.DRAFT:
        raise HTTPException(409, "only draft runs can be edited")
    _validate_run(body)
    for k, v in body.model_dump().items():
        if k == "keywords" and not v:
            continue
        setattr(run, k, v)
    db.commit()
    run.estimate = await estimate_specs(db, run, plan_tasks(run))
    db.commit()
    return run_out(run)


@router.get("/runs")
def list_runs(db: Session = Depends(get_db)):
    runs = db.scalars(select(SearchRun).order_by(SearchRun.id.desc()).limit(100))
    return [run_out(r) | {"tasks": None, "progress": {"counts": (r.progress or {}).get("counts", {}),
                                                         "stage": (r.progress or {}).get("stage")}} for r in runs]


@router.post("/runs/{run_id}/start")
async def start(run_id: int, db: Session = Depends(get_db)):
    run = _get(db, SearchRun, run_id)
    try:
        await start_run(db, run)
    except RunError as exc:
        raise HTTPException(400, str(exc)) from None
    backend = await enqueue_run(run.id)
    return run_out(run) | {"queue": backend}


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    return run_out(_get(db, SearchRun, run_id))


@router.get("/runs/{run_id}/events")
async def run_events(run_id: int, request: Request):
    with SessionLocal() as db:
        _get(db, SearchRun, run_id)

    async def stream():
        last = None
        idle = 0
        while True:
            if await request.is_disconnected():
                return
            with SessionLocal() as db:
                run = db.get(SearchRun, run_id)
                payload = {"status": run.status, "progress": run.progress, "cost_usd": run.cost_usd,
                           "error": run.error, "round": run.round}
            body = json.dumps(payload, default=str)
            if body != last:
                last = body
                idle = 0
                yield f"event: progress\ndata: {body}\n\n"
            else:
                idle += 1
                if idle % 15 == 0:
                    yield ": keep-alive\n\n"
            if payload["status"] in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.DRAFT):
                yield f"event: done\ndata: {json.dumps({'status': payload['status']})}\n\n"
                return
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/runs/{run_id}/cancel")
async def cancel(run_id: int, db: Session = Depends(get_db)):
    run = _get(db, SearchRun, run_id)
    await cancel_run(db, run)
    return run_out(run)


class ExpandIn(BaseModel):
    confirm: bool = False


@router.post("/runs/{run_id}/expand")
async def expand(run_id: int, body: ExpandIn, db: Session = Depends(get_db)):
    run = _get(db, SearchRun, run_id)
    try:
        out = await expand_run(db, run, body.confirm)
    except RunError as exc:
        raise HTTPException(400, str(exc)) from None
    if out.get("started"):
        out["queue"] = await enqueue_run(run.id)
    return out


# ------------------------------------------------------------------ jobs

SORTS = {
    "score": lambda: Score.total.desc().nulls_last(),
    "-score": lambda: Score.total.asc().nulls_last(),
    "posted": lambda: Job.posted_date.desc().nulls_last(),
    "-posted": lambda: Job.posted_date.asc().nulls_last(),
    "prescore": lambda: Job.prescore.desc().nulls_last(),
    "company": lambda: Job.company.asc(),
    "title": lambda: Job.title.asc(),
}


@router.get("/runs/{run_id}/jobs")
def list_jobs(
    run_id: int,
    status: str = Query("final", description="final | verified_active | uncertain | inactive | unverified | "
                                               "filtered | duplicates | all | shortlisted | applied | rejected"),
    platform: str | None = None,
    min_score: int | None = None,
    q: str | None = None,
    city: str | None = None,
    tier: str | None = None,
    category: str | None = None,
    sort: str = "score",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    run = _get(db, SearchRun, run_id)
    stmt = (select(Job).outerjoin(Verification).outerjoin(Score).where(Job.run_id == run_id))
    if status == "final":
        stmt = stmt.where(Job.filter_reason.is_(None), Job.duplicate_of.is_(None),
                          Verification.status == "verified_active", Score.total >= run.min_score)
        if run.exclude_linkedin_easy_apply:
            stmt = stmt.where(or_(Verification.easy_apply.is_(None), Verification.easy_apply.is_(False)))
    elif status in ("verified_active", "uncertain", "inactive"):
        stmt = stmt.where(Job.duplicate_of.is_(None), Verification.status == status)
    elif status == "unverified":
        stmt = stmt.where(Job.filter_reason.is_(None), Job.duplicate_of.is_(None), Verification.job_id.is_(None))
    elif status == "filtered":
        stmt = stmt.where(Job.filter_reason.is_not(None))
    elif status == "duplicates":
        stmt = stmt.where(Job.duplicate_of.is_not(None))
    elif status in ("shortlisted", "applied", "rejected"):
        stmt = stmt.where(Job.user_state == status)
    elif status != "all":
        raise HTTPException(400, f"unknown status {status}")
    if platform:
        stmt = stmt.where(Job.platform.in_(platform.split(",")))
    if min_score is not None:
        stmt = stmt.where(Score.total >= min_score)
    if city:
        stmt = stmt.where(Job.city.in_(city.split(",")))
    if tier:
        stmt = stmt.where(Score.company_tier == tier)
    if category:
        stmt = stmt.where(Score.category.in_(category.split(",")))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Job.title.ilike(like), Job.company.ilike(like), Job.description.ilike(like),
                              Score.key_skills_match.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = SORTS.get(sort, SORTS["score"])()
    rows = db.scalars(stmt.order_by(order, Job.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [job_row(j) for j in rows]}


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = _get(db, Job, job_id)
    out = job_detail(job)
    out["duplicates"] = [job_row(j) for j in db.scalars(select(Job).where(Job.duplicate_of == job_id))]
    return out


class JobPatch(BaseModel):
    user_state: Literal["shortlisted", "applied", "rejected"] | None = None
    user_note: str | None = Field(default=None, max_length=5000)


@router.patch("/jobs/{job_id}")
def patch_job(job_id: int, body: JobPatch, db: Session = Depends(get_db)):
    job = _get(db, Job, job_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(job, k, v)
    db.commit()
    return job_row(job)


@router.get("/runs/{run_id}/export.xlsx")
def export(run_id: int, full: bool = False, db: Session = Depends(get_db)):
    run = _get(db, SearchRun, run_id)
    jobs = final_jobs_query(db, run)
    data = build_workbook(jobs, full=full, run=run, profile=run.resume.parsed_profile)
    name = FILENAME if not full else FILENAME.replace(".xlsx", "_Full_Report.xlsx")
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
