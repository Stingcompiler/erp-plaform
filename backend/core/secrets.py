"""Encryption at rest for credentials the platform holds on a tenant's
behalf (a WhatsApp permanent token today).

Envelope: Fernet (AES-128-CBC + HMAC-SHA256, versioned, timestamped) with a
key from the environment. ``SECRETS_ENCRYPTION_KEY`` is the current key;
``SECRETS_ENCRYPTION_KEY_PREVIOUS`` may hold the one before it during a
rotation — values encrypted under either still decrypt, new values always
use the current key, and ``rotate()`` re-encrypts a value under the current
one. When no key is configured the key is derived from ``SECRET_KEY`` so a
development checkout works unchanged; production sets a dedicated key so a
leaked Django secret alone does not open the credential store.

Stored values are prefixed ``enc:v1:`` so a plaintext left over from before
this module (or a column mix-up) is recognisable and never mistaken for a
ciphertext.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings

PREFIX = "enc:v1:"


class SecretUnreadable(Exception):
    """The stored value was encrypted under a key this process does not have."""


def _fernet_key(raw):
    """A Fernet key from any string: a real 32-byte urlsafe key is used as is,
    anything else is hashed into one (so an arbitrary passphrase works)."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        Fernet(raw.encode())
        return raw.encode()
    except (ValueError, TypeError):
        return base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())


def _keys():
    """Current key first (it encrypts), then the previous one, then the key
    derived from SECRET_KEY — always last, so rows sealed before a dedicated
    key was configured stay readable and ``rotate_secrets`` can re-seal
    them without the operator having to reconstruct the derived key."""
    derived = _fernet_key("vezano-secrets:" + settings.SECRET_KEY)
    current = _fernet_key(getattr(settings, "SECRETS_ENCRYPTION_KEY", "")) or derived
    previous = _fernet_key(getattr(settings, "SECRETS_ENCRYPTION_KEY_PREVIOUS", ""))
    keys = []
    for key in (current, previous, derived):
        if key and key not in keys:
            keys.append(key)
    return keys


def _multi():
    return MultiFernet([Fernet(k) for k in _keys()])


def is_dedicated_key_configured():
    return bool((getattr(settings, "SECRETS_ENCRYPTION_KEY", "") or "").strip())


def encrypt(value):
    """Plaintext → ``enc:v1:<token>``; empty stays empty (nothing to protect)."""
    value = value or ""
    if not value:
        return ""
    return PREFIX + _multi().encrypt(value.encode()).decode()


def is_encrypted(stored):
    return bool(stored) and str(stored).startswith(PREFIX)


def decrypt(stored):
    """``enc:v1:<token>`` → plaintext. A value without the prefix is returned
    as is (legacy plaintext, migrated on next save); a ciphertext under an
    unknown key raises SecretUnreadable rather than silently returning junk."""
    stored = stored or ""
    if not stored:
        return ""
    if not is_encrypted(stored):
        return stored
    try:
        return _multi().decrypt(stored[len(PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise SecretUnreadable(
            "stored secret cannot be decrypted with the configured keys"
        ) from exc


def rotate(stored):
    """Re-encrypt under the current key (no-op for empty values)."""
    return encrypt(decrypt(stored))
