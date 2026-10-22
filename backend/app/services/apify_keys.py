"""Pool of Apify API keys: one key per calendar day, automatic failover, and a usage log.

Rotation: each day the active key that was used least recently is picked and kept for the whole day
(so ~30 keys cover a month). If it turns out invalid or out of credit, it is marked exhausted for the
day and the next key takes over. With an empty pool, APIFY_TOKEN from .env is used as before.
"""

import asyncio
import csv
import io
import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apify.client import ApifyClient, ApifyError, summarize_limits
from app.config import get_settings
from app.logging_setup import redact
from app.models import ApifyKey, ApifyKeyDay, ApifyKeyUsage
from app.security import SecretError, decrypt, encrypt, fingerprint, mask

log = logging.getLogger("apify_keys")

TOKEN_RE = re.compile(r"apify_api_[A-Za-z0-9]{20,}")
ENV_LABEL = "APIFY_TOKEN (.env)"


class KeyPoolError(Exception):
    pass


@dataclass
class ResolvedKey:
    key_id: int | None  # None = the .env APIFY_TOKEN
    label: str
    token: str

    @property
    def masked(self) -> str:
        return mask(self.token[-4:])


def today() -> date:
    return datetime.now(ZoneInfo(get_settings().key_rotation_tz)).date()


def _env_token() -> str | None:
    t = get_settings().apify_token
    return t.get_secret_value() if t and t.get_secret_value() else None


def _remaining(k: ApifyKey) -> float | None:
    if k.monthly_limit_usd is None or k.monthly_usage_usd is None:
        return None
    return round(max(k.monthly_limit_usd - k.monthly_usage_usd, 0.0), 4)


def key_out(k: ApifyKey, uses: int = 0, today_id: int | None = None, spent: float = 0.0) -> dict:
    d = today()
    return {
        "id": k.id, "label": k.label, "masked": mask(k.last4), "active": k.active,
        "exhausted_today": k.exhausted_on == d, "last_error": k.last_error,
        "last_used_on": k.last_used_on, "created_at": k.created_at, "uses": uses,
        "is_today": k.id == today_id,
        "account": k.account, "monthly_usage_usd": k.monthly_usage_usd, "monthly_limit_usd": k.monthly_limit_usd,
        "remaining_usd": _remaining(k), "usage_checked_at": k.usage_checked_at,
        "spent_by_jobradar_usd": round(spent, 4),
    }


# ------------------------------------------------------------------ CRUD


def validate_token(token: str) -> str:
    token = (token or "").strip()
    if not TOKEN_RE.fullmatch(token):
        raise KeyPoolError("That doesn't look like an Apify API token (expected apify_api_ followed by letters/digits)")
    return token


def add_key(db: Session, token: str, label: str | None = None) -> ApifyKey:
    token = validate_token(token)
    h = fingerprint(token)
    if db.scalar(select(ApifyKey.id).where(ApifyKey.token_hash == h)):
        raise KeyPoolError("This key is already in the pool")
    n = (db.scalar(select(func.count(ApifyKey.id))) or 0) + 1
    key = ApifyKey(label=(label or "").strip()[:200] or f"Key {n}", token_enc=encrypt(token), token_hash=h,
                   last4=token[-4:], active=True)
    db.add(key)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise KeyPoolError("This key is already in the pool") from None
    return key


def import_keys(db: Session, filename: str, data: bytes) -> dict:
    """Read every apify_api_… token from an .xlsx or .csv file. A text cell in the same row becomes the label."""
    rows: list[list[str]] = []
    name = filename.lower()
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                rows.append(["" if v is None else str(v).strip() for v in row])
        wb.close()
    elif name.endswith(".csv") or name.endswith(".txt"):
        text = data.decode("utf-8-sig", errors="replace")
        rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text))]
    else:
        raise KeyPoolError("Upload an .xlsx or .csv file (old .xls files: re-save as .xlsx)")

    added, duplicates, found = 0, 0, 0
    labels: list[str] = []
    for row in rows:
        tokens = [m for cell in row for m in TOKEN_RE.findall(cell)]
        if not tokens:
            continue
        others = [c for c in row if c and not TOKEN_RE.search(c)]
        for i, token in enumerate(tokens):
            found += 1
            label = others[0] if others else None
            if label and len(tokens) > 1:
                label = f"{label} #{i + 1}"
            try:
                k = add_key(db, token, label)
                added += 1
                labels.append(k.label)
            except KeyPoolError:
                duplicates += 1
    if not found:
        raise KeyPoolError("No Apify tokens (apify_api_…) found in the file")
    return {"found": found, "added": added, "duplicates": duplicates, "labels": labels}


def delete_key(db: Session, key_id: int) -> None:
    key = db.get(ApifyKey, key_id)
    if key is None:
        raise KeyPoolError("key not found")
    db.delete(key)  # usage rows keep the label snapshot; FKs are SET NULL
    db.commit()


def update_key(db: Session, key_id: int, label: str | None = None, active: bool | None = None) -> ApifyKey:
    key = db.get(ApifyKey, key_id)
    if key is None:
        raise KeyPoolError("key not found")
    if label is not None and label.strip():
        key.label = label.strip()[:200]
    if active is not None:
        key.active = active
        if active:
            key.exhausted_on = None
            key.last_error = None
    db.commit()
    return key


def log_usage(db: Session, key: ResolvedKey | ApifyKey | None, event: str, run_id: int | None = None,
              detail: str | None = None) -> None:
    key_id = getattr(key, "key_id", None) if isinstance(key, ResolvedKey) else getattr(key, "id", None)
    label = key.label if key is not None else ENV_LABEL
    db.add(ApifyKeyUsage(key_id=key_id, key_label=label, day=today(), at=datetime.now(UTC), event=event,
                         run_id=run_id, detail=redact(detail)[:1000] if detail else None))
    db.commit()


# ------------------------------------------------------------------ daily pick


def _usable(db: Session, d: date):
    return db.scalars(
        select(ApifyKey)
        .where(ApifyKey.active.is_(True), (ApifyKey.exhausted_on.is_(None)) | (ApifyKey.exhausted_on != d))
        .order_by(ApifyKey.last_used_on.is_not(None), ApifyKey.last_used_on, ApifyKey.id)
    ).all()


def _resolved(key: ApifyKey) -> ResolvedKey:
    try:
        return ResolvedKey(key.id, key.label, decrypt(key.token_enc))
    except SecretError as exc:
        raise KeyPoolError(f"{key.label}: {exc}") from None


def has_pool(db: Session) -> bool:
    return bool(db.scalar(select(func.count(ApifyKey.id)).where(ApifyKey.active.is_(True))))


def has_any_token(db: Session) -> bool:
    return has_pool(db) or _env_token() is not None


def current_key(db: Session) -> ResolvedKey | None:
    """Today's key (picking one if none is assigned yet). Falls back to APIFY_TOKEN when the pool is empty."""
    d = today()
    if not has_pool(db):
        tok = _env_token()
        return ResolvedKey(None, ENV_LABEL, tok) if tok else None
    day = db.get(ApifyKeyDay, d)
    if day and day.key_id:
        key = db.get(ApifyKey, day.key_id)
        if key and key.active and key.exhausted_on != d:
            return _resolved(key)
    return _pick(db, d, reason="daily rotation")


def _pick(db: Session, d: date, reason: str) -> ResolvedKey | None:
    candidates = _usable(db, d)
    if not candidates:
        return None
    key = candidates[0]
    key.last_used_on = d
    day = db.get(ApifyKeyDay, d)
    if day is None:
        db.add(ApifyKeyDay(day=d, key_id=key.id, picked_at=datetime.now(UTC)))
    else:
        day.key_id = key.id
        day.picked_at = datetime.now(UTC)
    db.commit()
    log_usage(db, key, "daily_pick", detail=reason)
    return _resolved(key)


def failover(db: Session, key: ResolvedKey, reason: str, run_id: int | None = None) -> ResolvedKey | None:
    """Mark `key` unusable for today and switch today's assignment to the next key."""
    if key.key_id is None:
        return None  # .env token: nothing to switch to
    d = today()
    row = db.get(ApifyKey, key.key_id)
    if row is not None:
        row.exhausted_on = d
        row.last_error = redact(reason)[:500]
        db.commit()
    log_usage(db, key, "failover", run_id=run_id, detail=reason)
    nxt = _pick(db, d, reason=f"failover from {key.label}")
    if nxt is None:
        log.warning("no usable Apify keys left today")
    return nxt


def token_for(db: Session, key_id: int | None) -> ResolvedKey | None:
    """The key that started an existing Apify run (needed to wait for it and read its dataset)."""
    if key_id is None:
        tok = _env_token()
        return ResolvedKey(None, ENV_LABEL, tok) if tok else None
    key = db.get(ApifyKey, key_id)
    return _resolved(key) if key else None


async def key_with_credit(db: Session, needed_usd: float, run_id: int | None = None
                          ) -> tuple[ResolvedKey | None, float | None, str | None]:
    """Today's key, failing over while a key's remaining monthly credit is below `needed_usd`.

    Returns (key, remaining credit or None if unknown, error note)."""
    key = current_key(db)
    tried = 0
    while key is not None and tried < 40:
        tried += 1
        try:
            async with ApifyClient(key.token) as client:
                remaining = summarize_limits(await client.limits())["remaining_usd"]
        except ApifyError as exc:
            if key.key_id is None:
                return key, None, redact(exc)
            key = failover(db, key, f"credit check failed: {exc}", run_id)
            continue
        except Exception as exc:  # noqa: BLE001 - network problems: keep the key, credit unknown
            return key, None, redact(f"{type(exc).__name__}: {exc}")
        if remaining is not None and remaining < needed_usd and key.key_id is not None:
            key = failover(db, key, f"remaining credit ${remaining:.2f} < needed ${needed_usd:.2f}", run_id)
            continue
        return key, remaining, None
    return None, None, "no Apify key with enough credit today" if has_pool(db) else "APIFY_TOKEN not configured"


def _spent_by_key(db: Session) -> dict[int, float]:
    from app.models import ScrapeTask  # local import: models imports nothing from here

    rows = db.execute(
        select(ScrapeTask.apify_key_id, func.coalesce(func.sum(ScrapeTask.cost_usd), 0.0))
        .where(ScrapeTask.apify_key_id.is_not(None)).group_by(ScrapeTask.apify_key_id)
    ).all()
    return {k: float(v or 0) for k, v in rows}


def summary(db: Session) -> dict:
    d = today()
    keys = db.scalars(select(ApifyKey).order_by(ApifyKey.id)).all()
    uses = dict(db.execute(
        select(ApifyKeyUsage.key_id, func.count()).where(ApifyKeyUsage.event == "run").group_by(ApifyKeyUsage.key_id)
    ).all())
    spent = _spent_by_key(db)
    day = db.get(ApifyKeyDay, d)
    checked = [k for k in keys if k.usage_checked_at is not None]
    return {
        "today": d,
        "timezone": get_settings().key_rotation_tz,
        "today_key_id": day.key_id if day else None,
        "env_fallback": _env_token() is not None,
        "keys": [key_out(k, uses.get(k.id, 0), day.key_id if day else None, spent.get(k.id, 0.0)) for k in keys],
        "usable_today": len(_usable(db, d)),
        "totals": {
            "checked_keys": len(checked),
            "monthly_usage_usd": round(sum(k.monthly_usage_usd or 0 for k in checked), 4),
            "monthly_limit_usd": round(sum(k.monthly_limit_usd or 0 for k in checked), 2),
            "remaining_usd": round(sum(_remaining(k) or 0 for k in checked), 4),
            "spent_by_jobradar_usd": round(sum(spent.values()), 4),
            "last_checked_at": max((k.usage_checked_at for k in checked), default=None),
        },
    }


# ------------------------------------------------------------------ connection tests


def _usage_text(r: dict) -> str:
    if not r.get("connected"):
        return f"FAILED: {r.get('error')}"
    parts = [f"account {r.get('username')}"]
    if r.get("plan"):
        parts.append(f"plan {r['plan']}")
    if r.get("monthly_limit_usd"):
        parts.append(f"${r.get('monthly_usage_usd', 0):.2f} used of ${r['monthly_limit_usd']:.2f} this month")
        if r.get("remaining_usd") is not None:
            parts.append(f"${r['remaining_usd']:.2f} left")
    return "OK: " + " · ".join(parts)


async def _probe(token: str) -> dict:
    """GET /users/me + /users/me/limits. No database access, so many can run concurrently."""
    try:
        async with ApifyClient(token) as client:
            me = await client.me()
            limits = summarize_limits(await client.limits())
    except ApifyError as exc:
        return {"connected": False, "error": redact(exc)[:300]}
    except Exception as exc:  # noqa: BLE001 - network failures
        return {"connected": False, "error": redact(f"{type(exc).__name__}: {exc}")[:300]}
    plan = me.get("plan") or {}
    return {"connected": True, "username": me.get("username"),
            "plan": plan.get("id") if isinstance(plan, dict) else plan, **limits}


def _store(db: Session, key: ResolvedKey, result: dict, log_prefix: str = "") -> dict:
    """Save the usage snapshot on the key row and log the test."""
    row = db.get(ApifyKey, key.key_id) if key.key_id is not None else None
    if row is not None:
        if result["connected"]:
            row.account = (result.get("username") or "")[:200] or None
            row.monthly_usage_usd = result.get("monthly_usage_usd")
            row.monthly_limit_usd = result.get("monthly_limit_usd") or None
            if row.exhausted_on != today():
                row.last_error = None
        else:
            row.last_error = result["error"]
        row.usage_checked_at = datetime.now(UTC)
        db.commit()
    result["detail"] = _usage_text(result)
    log_usage(db, key, "test", detail=log_prefix + result["detail"])
    return {"key_id": key.key_id, "label": key.label, "masked": key.masked, **result}


async def check_key(db: Session, key: ResolvedKey) -> dict:
    """Test one key, store its usage snapshot and log it."""
    return _store(db, key, await _probe(key.token))


async def check_all(db: Session, concurrency: int = 5) -> dict:
    """Test every pooled key (active or not), a few at a time."""
    resolved: list[ResolvedKey] = []
    results: list[dict] = []
    for r in db.scalars(select(ApifyKey).order_by(ApifyKey.id)).all():
        try:
            resolved.append(_resolved(r))
        except KeyPoolError as exc:
            results.append({"key_id": r.id, "label": r.label, "masked": mask(r.last4), "connected": False,
                            "error": str(exc), "detail": f"FAILED: {exc}"})
    sem = asyncio.Semaphore(concurrency)

    async def limited(k: ResolvedKey) -> dict:
        async with sem:
            return await _probe(k.token)

    probes = await asyncio.gather(*(limited(k) for k in resolved))
    results = [_store(db, k, pr, "[test all] ") for k, pr in zip(resolved, probes, strict=True)] + results
    ok = [r for r in results if r["connected"]]
    return {
        "tested": len(results),
        "ok": len(ok),
        "failed": len(results) - len(ok),
        "remaining_usd": round(sum(r.get("remaining_usd") or 0 for r in ok), 4),
        "results": results,
    }


def record_run_spend(db: Session, run_id: int, key_id: int | None, tasks: int, cost: float, items: int) -> None:
    """Add what a run spent on a key to that key's 'run' entry in the usage log."""
    row = db.scalar(
        select(ApifyKeyUsage).where(ApifyKeyUsage.run_id == run_id, ApifyKeyUsage.event == "run",
                                    ApifyKeyUsage.key_id.is_(key_id) if key_id is None
                                    else ApifyKeyUsage.key_id == key_id)
        .order_by(ApifyKeyUsage.id.desc())
    )
    text = f"{tasks} Apify runs · {items} items · ${cost:.3f} spent"
    if row is None:
        key = db.get(ApifyKey, key_id) if key_id else None
        db.add(ApifyKeyUsage(key_id=key_id, key_label=key.label if key else ENV_LABEL, day=today(),
                             at=datetime.now(UTC), event="run", run_id=run_id, detail=text))
    else:
        row.detail = text
    db.commit()


def usage(db: Session, limit: int = 200) -> list[dict]:
    rows = db.scalars(select(ApifyKeyUsage).order_by(ApifyKeyUsage.id.desc()).limit(limit)).all()
    return [{"id": r.id, "key_id": r.key_id, "key_label": r.key_label, "day": r.day, "at": r.at, "event": r.event,
             "run_id": r.run_id, "detail": r.detail} for r in rows]
