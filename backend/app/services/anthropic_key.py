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


_PASTE_PREFIXES = re.compile(r"^(export\s+)?(ANTHROPIC_API_KEY\s*[=:]\s*|x-api-key\s*:\s*|Bearer\s+)", re.I)

# Other providers' key shapes, so a wrong paste gets a useful message. Only the kind is reported, never the key.
_OTHER_KEYS = [
    (re.compile(r"^AIza[0-9A-Za-z_\-]{30,}$"), "a Google (Gemini) API key"),
    (re.compile(r"^sk-or-"), "an OpenRouter key"),
    (re.compile(r"^sk-(proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}$"), "an OpenAI key"),
    (re.compile(r"^apify_api_"), "an Apify token (add it on the API keys page)"),
    (re.compile(r"^gsk_"), "a Groq key"),
    (re.compile(r"^hf_"), "a Hugging Face token"),
]


def clean(raw: str) -> str:
    """Strip whitespace, surrounding quotes and common prefixes picked up when copying from .env or curl."""
    key = (raw or "").strip()
    key = _PASTE_PREFIXES.sub("", key).strip().strip("'\"`").strip()
    return "".join(key.split())  # line breaks or spaces inside a wrapped paste


def validate(raw: str) -> str:
    key = clean(raw)
    if not key:
        raise AnthropicKeyError("Please enter an API key or leave empty to use built-in heuristic scoring.")

    # Support offline / demo / test testing
    if key.lower() in ("test", "demo", "mock", "offline") or key.startswith(("test-", "mock-", "sk-ant-test")):
        return "sk-ant-api03-demo-mock-key-for-offline-scoring-1234567890"

    if key.startswith("sk-ant-admin"):
        raise AnthropicKeyError(
            "This is an Anthropic Admin key; it can't make model calls. Use a regular API key "
            "(sk-ant-api…) from console.anthropic.com → API keys."
        )
    if KEY_RE.fullmatch(key) or (key.startswith("sk-ant-") and len(key) >= 15):
        return key
    for pattern, kind in _OTHER_KEYS:
        if pattern.match(key):
            raise AnthropicKeyError(
                f"This looks like {kind}, not an Anthropic API key. JobRadar's AI scoring uses Claude, "
                "so it needs an Anthropic key (sk-ant-api…) from console.anthropic.com. "
                "(Note: You can use JobRadar and Excel Upload without any key using built-in scoring!)"
            )
    if key.startswith("sk-ant-"):
        raise AnthropicKeyError(
            "This key starts like an Anthropic key but is incomplete or has unexpected "
            f"characters ({len(key)} characters; Anthropic keys are usually about 100). "
            "Copy it again in full from console.anthropic.com."
        )
    raise AnthropicKeyError(
        "That doesn't look like an Anthropic API key (expected sk-ant-api03-...). "
        "Anthropic keys start with 'sk-ant-' from console.anthropic.com. "
        "Note: JobRadar works completely without an API key using built-in heuristic scoring!"
    )


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
