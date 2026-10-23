"""Google AI Studio (Gemini) API key stored encrypted in app_settings, same pattern as anthropic_key.py."""

import re

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import AppSetting
from app.security import SecretError, decrypt, encrypt

SETTING_KEY = "google_api_key_enc"
# Google AI Studio keys: old format AIzaSy... or newer AQ. format
KEY_RE = re.compile(r"(AIza[0-9A-Za-z_\-]{30,}|AQ\.Ab[0-9A-Za-z_\-\.]{20,})")


class GoogleKeyError(Exception):
    pass


def clean(raw: str) -> str:
    key = (raw or "").strip().strip("'\"`").strip()
    return "".join(key.split())


def validate(raw: str) -> str:
    key = clean(raw)
    if not key:
        raise GoogleKeyError("Please enter a Google AI Studio API key.")
    if KEY_RE.fullmatch(key):
        return key
    # Also accept any key that starts with AQ. (newer Gemini API key format from aistudio.google.com)
    if key.startswith("AQ."):
        return key
    raise GoogleKeyError(
        "That doesn't look like a Google AI Studio API key. "
        "Expected a key starting with 'AIza...' or 'AQ.' from https://aistudio.google.com/apikey"
    )


def detect(raw: str) -> bool:
    """Return True if the raw string looks like a Google AI key."""
    key = clean(raw)
    return key.startswith("AIza") or key.startswith("AQ.")


def _stored(db: Session) -> dict | None:
    row = db.get(AppSetting, SETTING_KEY)
    return row.value if row is not None and isinstance(row.value, dict) else None


def resolve(db: "Session | None" = None) -> "tuple[str | None, str | None]":
    """(api key, source) where source is 'ui', 'env' or None."""
    if db is None:
        with SessionLocal() as s:
            return resolve(s)
    stored = _stored(db)
    if stored and stored.get("enc"):
        try:
            return decrypt(stored["enc"]), "ui"
        except SecretError:
            pass
    env = get_settings().google_api_key
    if env and env.get_secret_value():
        return env.get_secret_value(), "env"
    return None, None


def status(db: Session) -> dict:
    key, source = resolve(db)
    stored = _stored(db) or {}
    masked = None
    if key:
        # Show first 6 chars + last 4 for AQ. format, or AIza prefix + last 4
        if key.startswith("AQ."):
            masked = f"AQ.••••{key[-4:]}"
        else:
            masked = f"AIza••••{key[-4:]}"
    return {
        "configured": key is not None,
        "source": source,
        "masked": masked,
        "saved_at": stored.get("saved_at") if source == "ui" else None,
        "env_available": bool(get_settings().google_api_key),
        "unreadable": bool(stored.get("enc")) and source != "ui",
    }


def save(db: Session, key: str, saved_at: str) -> None:
    value = {"enc": encrypt(key), "saved_at": saved_at}
    row = db.get(AppSetting, SETTING_KEY)
    if row is None:
        db.add(AppSetting(key=SETTING_KEY, value=value))
    else:
        row.value = value
    db.commit()


def remove(db: Session) -> bool:
    row = db.get(AppSetting, SETTING_KEY)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
