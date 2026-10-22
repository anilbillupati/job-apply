"""Endpoints for the Apify key pool, the seen-jobs history and company exclusions."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.apify.client import ApifyClient, ApifyError, summarize_limits
from app.db import get_db
from app.logging_setup import redact
from app.models import ApifyKey, SeenJob
from app.services import apify_keys as keys
from app.services import app_settings

router = APIRouter()

MAX_KEY_FILE_BYTES = 5 * 1024 * 1024


# ------------------------------------------------------------------ Apify keys


@router.get("/apify/keys")
def list_keys(db: Session = Depends(get_db)):
    return keys.summary(db)


class KeyIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    label: str | None = Field(default=None, max_length=200)


@router.post("/apify/keys")
def add_key(body: KeyIn, db: Session = Depends(get_db)):
    try:
        key = keys.add_key(db, body.token, body.label)
    except keys.KeyPoolError as exc:
        raise HTTPException(400, str(exc)) from None
    return keys.key_out(key)


@router.post("/apify/keys/import")
async def import_keys(file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await file.read()
    if len(data) > MAX_KEY_FILE_BYTES:
        raise HTTPException(413, "file is larger than 5 MB")
    try:
        return keys.import_keys(db, file.filename or "keys.xlsx", data)
    except keys.KeyPoolError as exc:
        raise HTTPException(400, str(exc)) from None
    except Exception as exc:  # noqa: BLE001 - corrupt spreadsheets
        raise HTTPException(400, f"could not read the file: {redact(exc)}") from None


class KeyPatch(BaseModel):
    label: str | None = Field(default=None, max_length=200)
    active: bool | None = None


@router.patch("/apify/keys/{key_id}")
def update_key(key_id: int, body: KeyPatch, db: Session = Depends(get_db)):
    try:
        return keys.key_out(keys.update_key(db, key_id, body.label, body.active))
    except keys.KeyPoolError as exc:
        raise HTTPException(404, str(exc)) from None


@router.delete("/apify/keys/{key_id}")
def delete_key(key_id: int, db: Session = Depends(get_db)):
    try:
        keys.delete_key(db, key_id)
    except keys.KeyPoolError as exc:
        raise HTTPException(404, str(exc)) from None
    return {"ok": True}


async def _check(key: keys.ResolvedKey) -> dict:
    try:
        async with ApifyClient(key.token) as client:
            me = await client.me()
            limits = summarize_limits(await client.limits())
    except ApifyError as exc:
        return {"connected": False, "error": redact(exc)}
    except Exception as exc:  # noqa: BLE001 - network failures
        return {"connected": False, "error": redact(f"{type(exc).__name__}: {exc}")}
    plan = me.get("plan") or {}
    return {"connected": True, "username": me.get("username"),
            "plan": plan.get("id") if isinstance(plan, dict) else plan, **limits}


@router.post("/apify/keys/{key_id}/test")
async def test_key(key_id: int, db: Session = Depends(get_db)):
    if db.get(ApifyKey, key_id) is None:
        raise HTTPException(404, "key not found")
    key = keys.token_for(db, key_id)
    result = await _check(key)
    keys.log_usage(db, key, "test", detail="ok" if result["connected"] else result.get("error"))
    return {"key_id": key_id, "label": key.label, "masked": key.masked, **result}


@router.get("/apify/keys/today")
async def todays_key(check: bool = False, db: Session = Depends(get_db)):
    """Today's key (picked now if not yet assigned). With check=true, also its account and credit."""
    try:
        key = keys.current_key(db)
    except keys.KeyPoolError as exc:
        raise HTTPException(500, str(exc)) from None
    if key is None:
        return {"configured": False, "day": keys.today()}
    out = {"configured": True, "day": keys.today(), "key_id": key.key_id, "label": key.label, "masked": key.masked,
           "source": "pool" if key.key_id else "env"}
    if check:
        out |= await _check(key)
    return out


@router.get("/apify/keys/usage")
def key_usage(limit: int = 200, db: Session = Depends(get_db)):
    return keys.usage(db, min(max(limit, 1), 1000))


# ------------------------------------------------------------------ seen jobs


@router.get("/seen-jobs")
def seen_jobs(limit: int = 50, db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(SeenJob)) or 0
    by_reason = dict(db.execute(select(SeenJob.reason, func.count()).group_by(SeenJob.reason)).all())
    recent = db.scalars(select(SeenJob).order_by(SeenJob.seen_at.desc()).limit(min(limit, 500))).all()
    return {
        "total": total,
        "by_reason": by_reason,
        "recent": [{"platform": s.platform, "platform_job_id": s.platform_job_id, "title": s.title,
                    "company": s.company, "reason": s.reason, "first_run_id": s.first_run_id,
                    "seen_at": s.seen_at} for s in recent],
    }


@router.delete("/seen-jobs")
def clear_seen_jobs(db: Session = Depends(get_db)):
    n = db.execute(delete(SeenJob)).rowcount
    db.commit()
    return {"ok": True, "deleted": n}


@router.delete("/seen-jobs/{platform}/{platform_job_id}")
def forget_seen_job(platform: str, platform_job_id: str, db: Session = Depends(get_db)):
    row = db.get(SeenJob, (platform, platform_job_id))
    if row is None:
        raise HTTPException(404, "not in the seen history")
    db.delete(row)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ excluded companies


class CompaniesIn(BaseModel):
    companies: list[str] = Field(max_length=1000)


def _clean(companies: list[str]) -> list[str]:
    out: list[str] = []
    for c in companies:
        c = c.strip()[:200]
        if c and c.lower() not in {x.lower() for x in out}:
            out.append(c)
    return out


@router.get("/settings/excluded-companies")
def get_excluded(db: Session = Depends(get_db)):
    return {"companies": app_settings.get_setting(db, "excluded_companies") or []}


@router.put("/settings/excluded-companies")
def put_excluded(body: CompaniesIn, db: Session = Depends(get_db)):
    app_settings.update_settings(db, {"excluded_companies": _clean(body.companies)})
    return {"companies": app_settings.get_setting(db, "excluded_companies")}


@router.post("/settings/excluded-companies/add")
def add_excluded(body: CompaniesIn, db: Session = Depends(get_db)):
    current = app_settings.get_setting(db, "excluded_companies") or []
    app_settings.update_settings(db, {"excluded_companies": _clean([*current, *body.companies])})
    return {"companies": app_settings.get_setting(db, "excluded_companies")}
