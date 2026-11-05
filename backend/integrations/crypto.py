"""Token encryption at rest (ARCHITECTURE section 9, D63). MultiFernet over
`settings.INTEGRATION_ENCRYPTION_KEYS`, newest key first: new ciphertext uses the first key, any
listed key decrypts, and `rotate()` re-encrypts under the first key."""

from functools import cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@cache
def _fernet(keys: tuple[str, ...]) -> MultiFernet:
    if not keys:
        raise ImproperlyConfigured("INTEGRATION_ENCRYPTION_KEYS is empty.")
    try:
        return MultiFernet([Fernet(k) for k in keys])
    except (ValueError, TypeError):
        # never echo the key material
        raise ImproperlyConfigured(
            "INTEGRATION_ENCRYPTION_KEYS holds a malformed key "
            "(each must be Fernet.generate_key() output)."
        ) from None


def fernet() -> MultiFernet:
    return _fernet(tuple(settings.INTEGRATION_ENCRYPTION_KEYS))


def encrypt(plaintext: str) -> str:
    return fernet().encrypt(plaintext.encode()).decode() if plaintext else ""


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise ImproperlyConfigured(
            "A stored integration token cannot be decrypted with any configured key."
        ) from None


def rotate(ciphertext: str) -> str:
    return fernet().rotate(ciphertext.encode()).decode() if ciphertext else ""
