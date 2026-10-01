"""Email one-time codes, reusable by any public flow (purpose-scoped).

Owner decisions (2026-10-01): a 6-digit code, valid 10 minutes, 5 tries,
a new code after 60 seconds at the earliest, at most 3 codes an hour per
subject (an email address) and per client address. Used by the trial form
(website.trial_requests) and vezano.app/track/ (website.request_tracking);
built to carry password reset next.

    challenge_id = otp.issue("trial", email, payload={...}, request=request,
                             deliver=lambda code: otp.send_code_email(...))
    payload = otp.verify(challenge_id, code, purpose="trial")  # or raises
    payload = otp.resend(challenge_id, purpose="trial", request=request,
                         deliver=...)

Nothing here is a database row (production refuses migrations): a
challenge lives in Django's cache — the shared ``DatabaseCache`` in
production, so every gunicorn worker sees it; LocMem in tests — and the
code itself is never stored, only an HMAC-SHA256 of it keyed from
SECRET_KEY and the purpose, compared in constant time. Codes are never
logged. Errors are typed (``Expired``, ``WrongCode``, ``TooManyAttempts``,
``Cooldown``, ``TooManySends``, ``DeliveryFailed``) so each flow answers in
its own words.
"""

import hashlib
import hmac
import logging
import secrets
import time

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CODE_DIGITS = 6
CODE_TTL = 10 * 60  # seconds a code stays valid
MAX_ATTEMPTS = 5  # wrong codes before the challenge is thrown away
RESEND_AFTER = 60  # seconds before another code may be sent
HOURLY_SENDS = 3  # codes an hour per subject and per client address
SEND_WINDOW = 60 * 60

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


# ---------------------------------------------------------------- errors

class OtpError(Exception):
    code = "otp_error"


class Expired(OtpError):
    """Unknown, expired, used up, or issued for another purpose."""
    code = "code_expired"


class WrongCode(OtpError):
    code = "wrong_code"

    def __init__(self, attempts_left):
        super().__init__(self.code)
        self.attempts_left = attempts_left


class TooManyAttempts(OtpError):
    code = "too_many_attempts"


class _Wait(OtpError):
    def __init__(self, retry_after):
        super().__init__(self.code)
        self.retry_after = retry_after


class Cooldown(_Wait):
    code = "resend_cooldown"


class TooManySends(_Wait):
    code = "too_many_codes"


class DeliveryFailed(OtpError):
    code = "email_unavailable"


# ---------------------------------------------------------------- primitives

def now():
    """The clock every expiry here reads; tests move it instead of sleeping."""
    return time.time()


def new_code():
    return f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"


def new_id():
    return secrets.token_urlsafe(24)


def _key():
    return hashlib.sha256(f"vezano-otp:{settings.SECRET_KEY}".encode()).digest()


def code_hash(purpose, code):
    """HMAC-SHA256 of ``code`` for ``purpose``; the only form a code is kept in."""
    return hmac.new(_key(), f"{purpose}:{code}".encode(), hashlib.sha256).hexdigest()


def normalise_code(value):
    """The six digits a visitor typed or pasted ("123 456", "١٢٣٤٥٦"), or ""."""
    digits = "".join(ch for ch in str(value or "").translate(_ARABIC_DIGITS) if ch.isdigit())
    return digits if len(digits) == CODE_DIGITS else ""


def mask_email(email):
    """``m•••@gmail.com``: enough for the owner to recognise the address."""
    local, _sep, domain = str(email or "").strip().partition("@")
    if not local or not domain:
        return ""
    return f"{local[0]}•••@{domain.lower()}"


def _digest(value):
    return hashlib.sha256(str(value or "").strip().lower().encode()).hexdigest()[:32]


# ---------------------------------------------------------------- hourly budgets

def _budget_key(purpose, scope):
    return f"otp-sends:{purpose}:{scope}"


def _used(key):
    cutoff = now() - SEND_WINDOW
    return [stamp for stamp in (cache.get(key) or []) if stamp > cutoff]


def subject_scope(subject_key):
    """The budget scope of a subject (an email address; never stored as such)."""
    return _subject_scope(_digest(subject_key))


def _subject_scope(digest):
    return f"subject:{digest}"


def ip_scope(request):
    from core.activity import get_client_ip

    return f"ip:{get_client_ip(request) or 'unknown'}"


def retry_after(purpose, scope):
    """Seconds until ``scope`` may be sent another code (0 = now)."""
    used = sorted(_used(_budget_key(purpose, scope)))
    if len(used) < HOURLY_SENDS:
        return 0
    return max(1, int(used[-HOURLY_SENDS] + SEND_WINDOW - now() + 0.999))


def spend(purpose, scope):
    """Count one code sent to ``scope``."""
    key = _budget_key(purpose, scope)
    stamps = _used(key) + [now()]
    cache.set(key, stamps[-HOURLY_SENDS * 2:], SEND_WINDOW)


def check_budget(purpose, scopes):
    """Raise ``TooManySends`` when any of ``scopes`` used its hour."""
    wait = max([retry_after(purpose, scope) for scope in scopes] or [0])
    if wait:
        raise TooManySends(wait)


def _scopes(subject_digest, request):
    scopes = [_subject_scope(subject_digest)]
    if request is not None:
        scopes.append(ip_scope(request))
    return scopes


# ---------------------------------------------------------------- challenges

def _entry_key(challenge_id):
    return f"otp:{challenge_id}"


def _save(challenge_id, entry):
    ttl = max(1, int(entry["expires_at"] - now()) + 1)
    cache.set(_entry_key(challenge_id), entry, ttl)


def _load(challenge_id, purpose):
    if not challenge_id or not isinstance(challenge_id, str) or len(challenge_id) > 64:
        return None
    entry = cache.get(_entry_key(challenge_id))
    if not isinstance(entry, dict) or entry.get("purpose") != purpose:
        return None
    if entry.get("expires_at", 0) <= now():
        return None
    return entry


def drop(challenge_id):
    cache.delete(_entry_key(challenge_id))


def _deliver(deliver, code):
    try:
        return bool(deliver(code)) if deliver else False
    except Exception:  # noqa: BLE001 - logged without the code, reported as failed
        logger.exception("one-time code could not be delivered")
        return False


def issue(purpose, subject_key, payload=None, *, request=None, deliver=None):
    """A new challenge for ``subject_key``; ``deliver(code)`` sends the code
    (True when it went out). ``request`` adds the client address's hourly
    budget to the subject's; pass None when the caller counts the address
    itself. Raises ``TooManySends`` or ``DeliveryFailed`` (nothing kept)."""
    subject = _digest(subject_key)
    scopes = _scopes(subject, request)
    check_budget(purpose, scopes)
    code = new_code()
    moment = now()
    challenge_id = new_id()
    _save(challenge_id, {
        "purpose": purpose,
        "subject": subject,
        "payload": payload if payload is not None else {},
        "code_hash": code_hash(purpose, code),
        "attempts": 0,
        "sends": 1,
        "created_at": moment,
        "last_sent": moment,
        "expires_at": moment + CODE_TTL,
    })
    for scope in scopes:
        spend(purpose, scope)
    if not _deliver(deliver, code):
        drop(challenge_id)
        raise DeliveryFailed(DeliveryFailed.code)
    logger.info("otp issued purpose=%s", purpose)
    return challenge_id


def peek(challenge_id, *, purpose):
    """The live challenge's payload (no attempt counted), or raise ``Expired``."""
    entry = _load(challenge_id, purpose)
    if entry is None:
        raise Expired(Expired.code)
    return entry["payload"]


def verify(challenge_id, code, *, purpose, consume=True):
    """The payload when ``code`` is right; otherwise ``Expired``,
    ``WrongCode`` (with attempts_left) or ``TooManyAttempts`` (the
    challenge is then gone). A malformed code costs no attempt.
    ``consume=False`` keeps the challenge until it expires (a flow that
    answers a replayed verify itself)."""
    entry = _load(challenge_id, purpose)
    if entry is None:
        raise Expired(Expired.code)
    typed = normalise_code(code)
    if not typed:
        raise WrongCode(MAX_ATTEMPTS - int(entry.get("attempts") or 0))
    entry["attempts"] = int(entry.get("attempts") or 0) + 1
    right = hmac.compare_digest(str(entry.get("code_hash") or ""), code_hash(purpose, typed))
    if entry["attempts"] > MAX_ATTEMPTS:
        drop(challenge_id)
        raise TooManyAttempts(TooManyAttempts.code)
    if not right:
        if entry["attempts"] >= MAX_ATTEMPTS:
            drop(challenge_id)
            raise TooManyAttempts(TooManyAttempts.code)
        _save(challenge_id, entry)
        raise WrongCode(MAX_ATTEMPTS - entry["attempts"])
    if consume:
        drop(challenge_id)
    else:
        _save(challenge_id, entry)
    return entry["payload"]


def resend(challenge_id, *, purpose, request=None, deliver=None):
    """A new code for a live challenge (the old one stops working, the tries
    start over, the 10 minutes restart); its payload. Raises ``Expired``,
    ``Cooldown``, ``TooManySends`` or ``DeliveryFailed``."""
    entry = _load(challenge_id, purpose)
    if entry is None:
        raise Expired(Expired.code)
    wait = max(0, int(entry.get("last_sent", 0) + RESEND_AFTER - now() + 0.999))
    if wait:
        raise Cooldown(wait)
    scopes = _scopes(entry["subject"], request)
    check_budget(purpose, scopes)
    code = new_code()
    moment = now()
    entry.update({
        "code_hash": code_hash(purpose, code),
        "attempts": 0,
        "sends": int(entry.get("sends") or 0) + 1,
        "last_sent": moment,
        "expires_at": moment + CODE_TTL,
    })
    _save(challenge_id, entry)
    for scope in scopes:
        spend(purpose, scope)
    if not _deliver(deliver, code):
        raise DeliveryFailed(DeliveryFailed.code)
    logger.info("otp resent purpose=%s sends=%d", purpose, entry["sends"])
    return entry["payload"]


def stored(challenge_id):
    """The raw cache entry (tests and diagnostics: it never holds the code)."""
    return cache.get(_entry_key(challenge_id))


# ---------------------------------------------------------------- email

def send_code_email(recipient, code, *, subject_ar, subject_en, ar, en, primary=None,
                    preheader=None):
    """The branded bilingual email with ``code`` set large under the first
    half (core.mailer.send_bilingual). Keep the code out of the subject and
    the preheader: notification previews and logs show those."""
    from core import mailer

    minutes = CODE_TTL // 60
    return mailer.send_bilingual(
        subject_ar=subject_ar, subject_en=subject_en, ar=ar, en=en,
        preheader=preheader or (
            f"الرمز صالح {minutes} دقائق · The code is valid for {minutes} minutes"
        ),
        code=code, primary=primary, recipient=recipient,
    )
