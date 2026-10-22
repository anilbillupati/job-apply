"""Endpoints for the Apify key pool, the seen-jobs history and company exclusions."""

from datetime import UTC, datetime

import anthropic
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.apify.client import ApifyClient, ApifyError, summarize_limits
from app.db import get_db
from app.llm.client import make_client
from app.logging_setup import redact
from app.models import ApifyKey, SeenJob
from app.services import anthropic_key, app_settings
from app.services import apify_keys as keys

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


# ------------------------------------------------------------------ Anthropic key


async def _verify_anthropic(api_key: str) -> dict:
    """Cheap authenticated call (lists one model, no tokens used)."""
    try:
        client = make_client(api_key)
        page = await client.models.list(limit=1)
        await client.close()
        first = next(iter(page.data), None)
        return {"ok": True, "detail": f"key accepted (models visible, e.g. {first.id})" if first else "key accepted"}
    except anthropic.AuthenticationError:
        return {"ok": False, "auth_failed": True, "detail": "Anthropic rejected this key (invalid or revoked)"}
    except anthropic.PermissionDeniedError as exc:
        return {"ok": False, "auth_failed": True, "detail": redact(f"permission denied: {exc.message}")}
    except anthropic.APIError as exc:
        return {"ok": False, "detail": redact(f"{type(exc).__name__}: {exc}")[:300]}


@router.get("/settings/anthropic")
def anthropic_status(db: Session = Depends(get_db)):
    return anthropic_key.status(db)


class AnthropicKeyIn(BaseModel):
    api_key: str = Field(min_length=20, max_length=300)


@router.put("/settings/anthropic")
async def save_anthropic_key(body: AnthropicKeyIn, db: Session = Depends(get_db)):
    try:
        key = anthropic_key.validate(body.api_key)
    except anthropic_key.AnthropicKeyError as exc:
        raise HTTPException(400, str(exc)) from None
    check = await _verify_anthropic(key)
    if check.get("auth_failed"):
        raise HTTPException(400, check["detail"])
    anthropic_key.save(db, key, datetime.now(UTC).isoformat(timespec="seconds"))
    warning = None if check["ok"] else f"Saved, but the key could not be verified right now: {check['detail']}"
    return anthropic_key.status(db) | {"warning": warning}


@router.delete("/settings/anthropic")
def remove_anthropic_key(db: Session = Depends(get_db)):
    removed = anthropic_key.remove(db)
    return anthropic_key.status(db) | {"removed": removed}


@router.post("/settings/anthropic/test")
async def test_anthropic_key(db: Session = Depends(get_db)):
    key, source = anthropic_key.resolve(db)
    if key is None:
        return {"ok": False, "detail": "No Anthropic API key configured"}
    return await _verify_anthropic(key) | {"source": source}
