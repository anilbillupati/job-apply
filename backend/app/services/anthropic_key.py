"""Anthropic API key set from the UI, stored encrypted in app_settings. It takes priority over .env.

The row's key is not in app_settings.DEFAULTS, so GET /settings never returns it.
"""

import re

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import AppSetting
from app.security import SecretError, decrypt, encrypt

SETTING_KEY = "anthropic_api_key_enc"
KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")


class AnthropicKeyError(Exception):
    pass


def validate(key: str) -> str:
    key = (key or "").strip()
    if not KEY_RE.fullmatch(key):
        raise AnthropicKeyError("That doesn't look like an Anthropic API key (expected sk-ant-…)")
    return key


def _stored(db: Session) -> dict | None:
    row = db.get(AppSetting, SETTING_KEY)
    return row.value if row is not None and isinstance(row.value, dict) else None


def resolve(db: Session | None = None) -> tuple[str | None, str | None]:
    """(api key, source) where source is 'ui', 'env' or None."""
    if db is None:
        with SessionLocal() as s:
            return resolve(s)
    stored = _stored(db)
    if stored and stored.get("enc"):
        try:
            return decrypt(stored["enc"]), "ui"
        except SecretError:
            pass  # unreadable (secret key file replaced): fall back to .env
    env = get_settings().anthropic_api_key
    if env and env.get_secret_value():
        return env.get_secret_value(), "env"
    return None, None


def status(db: Session) -> dict:
    key, source = resolve(db)
    stored = _stored(db) or {}
    return {
        "configured": key is not None,
        "source": source,
        "masked": f"sk-ant-••••{key[-4:]}" if key else None,
        "saved_at": stored.get("saved_at") if source == "ui" else None,
        "env_available": bool(get_settings().anthropic_api_key),
        "unreadable": bool(stored.get("enc")) and source != "ui",
    }


def save(db: Session, key: str, saved_at: str) -> None:
    value = {"enc": encrypt(validate(key)), "saved_at": saved_at}
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
