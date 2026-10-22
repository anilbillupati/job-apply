"""Symmetric encryption for secrets stored in the database (pooled Apify keys).

The Fernet key comes from JOBRADAR_SECRET_KEY, or is generated once into SECRET_KEY_FILE
(default backend/.secret_key; /data/.secret_key in Docker). Losing that file makes stored keys unreadable.
"""

import hashlib
import os
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class SecretError(Exception):
    pass


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    if settings.secret_key:
        return Fernet(settings.secret_key.get_secret_value().encode())
    path = Path(settings.secret_key_file)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(Fernet.generate_key())
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return Fernet(path.read_bytes().strip())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        raise SecretError("stored key cannot be decrypted (was the secret key file replaced?)") from None


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def mask(last4: str) -> str:
    return f"apify_api_••••{last4}"
