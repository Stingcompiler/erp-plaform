"""Trial (R…) and demo (D…) requests on vezano.app/track/, behind an email code.

Owner decisions (2026-10-01). Any search key — the reference, the email,
the phone or the name — finds the visitor's requests with the matching
rules of website.platform_tracking (exact, last 90 days), but shows nothing
yet: a 6-digit code goes to the email stored ON THE REQUEST, never to an
address the visitor typed. Several matches with one email get one code;
matches with different emails each get their own code, and the code typed
decides which email's requests are shown. Requests without an email (a
demo request may have only a phone) get no code.

The answer to a search is the same whether anything matched or not: 202,
a fresh ``challenge_id`` and a hint. The hint shows a masked address only
when the visitor searched BY that email (so it tells them nothing they did
not type); otherwise it is empty and the page says "check the email you
used in your request".

A verified code returns that email's requests in full — status, the stages
with their dates, the team's public note and when it was written, the next
step — plus a signed view token good for 30 minutes, so a reload does not
need a new code. Store orders and subscription payments keep their own
search (POST /api/public/track/) exactly as before.
"""

import logging

from django.core import signing
from django.core.cache import cache
from django.db.models import Q

from core import otp
from website import platform_tracking, tracking

logger = logging.getLogger(__name__)

PURPOSE = "track"
VIEW_TTL = 30 * 60
VIEW_SALT = "vezano.track-requests.view"
# Never mail more addresses than this for one search.
MAX_EMAILS = 5
REFERENCE = platform_tracking.REFERENCE


# ---------------------------------------------------------------- matching

def _matching_rows(query):
    """[(kind, row)] of trial and demo requests a search finds."""
    found = tracking.classify(query, reference=REFERENCE)
    if found is None:
        return "none", []
    kind, value = found
    registrations = platform_tracking._registrations()
    demos = platform_tracking._demos()
    if kind == "reference":
        if value.startswith(("R", "D")):
            rows = registrations if value.startswith("R") else demos
            row = rows.filter(public_reference__iexact=value).first()
            if row is not None:
                return kind, [("registration" if value.startswith("R") else "demo", row)]
        # "Rashida" looks like a reference; a miss is a name.
        kind, value = "name", tracking.name_key(query)
    if not value:
        return kind, []
    if kind == "email":
        registrations = registrations.filter(email__iexact=value)
        demos = demos.filter(email__iexact=value)
    elif kind == "phone":
        registrations = registrations.filter(lookup_phone=value)
        demos = demos.filter(lookup_phone=value)
    else:
        registrations = registrations.filter(Q(lookup_name=value) | Q(lookup_company=value))
        demos = demos.filter(lookup_name=value)
    limit = tracking.LOOKUP_LIMIT
    return kind, (
        [("registration", row) for row in registrations[:limit]]
        + [("demo", row) for row in demos[:limit]]
    )


def _emails(rows):
    """The distinct stored addresses of ``rows``, in a stable order."""
    seen, emails = set(), []
    for _kind, row in rows:
        email = str(row.email or "").strip()
        if email and email.lower() not in seen:
            seen.add(email.lower())
            emails.append(email)
    return emails[:MAX_EMAILS]


# ---------------------------------------------------------------- codes
#
# One search may need several codes (one per stored address), so a search
# is a small bundle in the cache that names one core.otp challenge per
# address — none when nothing matched. The bundle carries the search's own
# tries, cooldown and expiry, so a miss behaves exactly like a match.

def _bundle_key(search_id):
    return f"track-search:{search_id}"


def _load(search_id):
    if not search_id or not isinstance(search_id, str) or len(search_id) > 64:
        return None
    bundle = cache.get(_bundle_key(search_id))
    if not isinstance(bundle, dict) or bundle.get("expires_at", 0) <= otp.now():
        return None
    return bundle


def _save(search_id, bundle):
    cache.set(_bundle_key(search_id), bundle, max(1, int(bundle["expires_at"] - otp.now()) + 1))


def _drop(search_id, bundle):
    for challenge_id in bundle.get("challenges") or []:
        otp.drop(challenge_id)
    cache.delete(_bundle_key(search_id))


def _email_code(email, code, language):
    minutes = otp.CODE_TTL // 60
    return otp.send_code_email(
        email, code,
        subject_ar="رمز متابعة طلبك في فيزانو برو",
        subject_en="Your Vezano Pro tracking code",
        ar=[
            "طلب أحدهم متابعة طلبك في فيزانو برو. رمز التحقق:",
            f"اكتبه في صفحة التتبّع خلال {minutes} دقائق. لا تشاركه مع أحد.",
            "إن لم تكن أنت فتجاهل الرسالة؛ لن يرى أحد طلبك دون هذا الرمز.",
        ],
        en=[
            "Someone asked to follow your Vezano Pro request. The code is shown above.",
            f"Enter it on the tracking page within {minutes} minutes. Never share it.",
            "If it was not you, ignore this email; nobody sees your request without it.",
        ],
        primary=language,
    )


def _deliver(email, language):
    return lambda code: _email_code(email, code, language)


def _hint(kind, query):
    if kind == "email":
        return otp.mask_email(" ".join(str(query).split()).replace(" ", ""))
    return ""


def _spend_address(request):
    """The client address's hourly budget, counted for EVERY search and
    resend — match or not — so a refusal tells nothing."""
    scope = otp.ip_scope(request)
    otp.check_budget(PURPOSE, [scope])
    otp.spend(PURPOSE, scope)


def start(query, language, request):
    """(search_id, response body). Raises core.otp.TooManySends past the
    client address's hourly budget."""
    _spend_address(request)
    kind, rows = _matching_rows(query)
    challenges = []
    for email in _emails(rows):
        try:
            # The address over its own hourly budget silently gets nothing.
            challenges.append(otp.issue(PURPOSE, email, {"email": email},
                                        deliver=_deliver(email, language)))
        except otp.OtpError:
            continue
    moment = otp.now()
    bundle = {
        "challenges": challenges,
        "attempts": 0,
        "language": language,
        "hint": _hint(kind, query),
        "last_sent": moment,
        "expires_at": moment + otp.CODE_TTL,
    }
    search_id = otp.new_id()
    _save(search_id, bundle)
    logger.info("track-requests challenge kind=%s matches=%d sent=%d",
                kind, len(rows), len(challenges))
    return search_id, body(search_id, bundle)


def body(search_id, bundle):
    """The one answer shape for a search or a resend."""
    return {
        "challenge_id": search_id,
        "sent_hint": bundle.get("hint") or "",
        "resend_after": otp.RESEND_AFTER,
    }


def resend(search_id, request):
    """New codes for a live search (core.otp errors: Expired, Cooldown,
    TooManySends)."""
    bundle = _load(search_id)
    if bundle is None:
        raise otp.Expired(otp.Expired.code)
    wait = max(0, int(bundle["last_sent"] + otp.RESEND_AFTER - otp.now() + 0.999))
    if wait:
        raise otp.Cooldown(wait)
    _spend_address(request)
    language = bundle.get("language") or "ar"
    sent = 0
    for challenge_id in bundle["challenges"]:
        try:
            email = otp.peek(challenge_id, purpose=PURPOSE)["email"]
            otp.resend(challenge_id, purpose=PURPOSE, deliver=_deliver(email, language))
            sent += 1
        except otp.OtpError:
            continue
    moment = otp.now()
    bundle.update({"attempts": 0, "last_sent": moment, "expires_at": moment + otp.CODE_TTL})
    _save(search_id, bundle)
    logger.info("track-requests resend sent=%d", sent)
    return body(search_id, bundle)


def verify(search_id, code):
    """The address the typed code was sent to; raises core.otp's Expired,
    WrongCode or TooManyAttempts — the same way for a search that matched
    nothing. Five tries per search, then it is gone."""
    bundle = _load(search_id)
    if bundle is None:
        raise otp.Expired(otp.Expired.code)
    typed = otp.normalise_code(code)
    if not typed:
        raise otp.WrongCode(otp.MAX_ATTEMPTS - int(bundle.get("attempts") or 0))
    bundle["attempts"] = int(bundle.get("attempts") or 0) + 1
    found = None
    if bundle["attempts"] <= otp.MAX_ATTEMPTS:
        for challenge_id in bundle["challenges"]:
            try:
                payload = otp.verify(challenge_id, typed, purpose=PURPOSE)
            except otp.OtpError:
                continue
            found = found or payload["email"]
    if found:
        _drop(search_id, bundle)
        return found
    if bundle["attempts"] >= otp.MAX_ATTEMPTS:
        _drop(search_id, bundle)
        raise otp.TooManyAttempts(otp.TooManyAttempts.code)
    _save(search_id, bundle)
    raise otp.WrongCode(otp.MAX_ATTEMPTS - bundle["attempts"])


# ---------------------------------------------------------------- the view

def view_token(email):
    return signing.dumps({"e": email, "x": int(otp.now() + VIEW_TTL)}, salt=VIEW_SALT)


def email_from_token(token):
    """The verified address a view token stands for, or None once expired."""
    try:
        data = signing.loads(str(token or ""), salt=VIEW_SALT)
    except signing.BadSignature:
        return None
    if not isinstance(data, dict) or int(data.get("x") or 0) <= otp.now():
        return None
    return data.get("e") or None


def token_expires_in(token):
    try:
        data = signing.loads(str(token or ""), salt=VIEW_SALT)
    except signing.BadSignature:
        return 0
    return max(0, int(data.get("x") or 0) - int(otp.now()))


def results(email, language):
    """Every trial and demo request (last 90 days) stored with ``email``."""
    registrations = list(platform_tracking._registrations().filter(email__iexact=email)
                         .select_related("plan_version__plan")[: tracking.LOOKUP_LIMIT])
    demos = list(platform_tracking._demos().filter(email__iexact=email)[: tracking.LOOKUP_LIMIT])
    history = _history(registrations, demos)
    items = [_registration_view(row, language, history) for row in registrations]
    items += [_demo_view(row, language, history) for row in demos]
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items[: tracking.LOOKUP_LIMIT]


STEP_LABELS = {
    "submitted": ("استلمنا الطلب", "Received"),
    "under_review": ("قيد المراجعة", "Under review"),
    "needs_information": ("نحتاج معلومات إضافية", "More information needed"),
    "approved": ("تمت الموافقة", "Approved"),
    "provisioned": ("تم التفعيل", "Activated"),
    "rejected": ("مرفوض", "Rejected"),
    "withdrawn": ("سُحب الطلب", "Withdrawn"),
    "new": ("استلمنا الطلب", "Received"),
    "contacted": ("تواصلنا معك", "We contacted you"),
    "qualified": ("قيد المتابعة", "In follow-up"),
    "closed": ("مغلق", "Closed"),
}
CLOSED_STEPS = {"rejected", "withdrawn", "closed"}


def _history(registrations, demos):
    """{(kind, pk): [(status, at), ...]} from the audit log, oldest first —
    the only record of when a request changed state. Plus, per
    registration, when its public note was last written."""
    from core.models import ActivityLog

    out = {}
    reg_ids = [str(row.pk) for row in registrations]
    demo_ids = [str(row.pk) for row in demos]
    logs = ActivityLog.objects.filter(
        Q(entity_type__in=["RegistrationRequest", "RegistrationProvision"],
          entity_id__in=reg_ids)
        | Q(entity_type="PlatformLead", entity_id__in=demo_ids)
    ).order_by("created_at", "id").only("entity_type", "entity_id", "action", "metadata",
                                        "created_at") if (reg_ids or demo_ids) else []
    for log in logs:
        meta = log.metadata if isinstance(log.metadata, dict) else {}
        if log.entity_type == "PlatformLead":
            status = meta.get("status_to")
            if status and status != meta.get("status_from"):
                out.setdefault(("demo", log.entity_id), []).append((status, log.created_at))
            continue
        key = ("registration", log.entity_id)
        if log.entity_type == "RegistrationProvision":
            out.setdefault(key, []).append(("provisioned", log.created_at))
        elif log.action == "approve":
            out.setdefault(key, []).append(("approved", log.created_at))
        elif meta.get("status"):
            out.setdefault(key, []).append((meta["status"], log.created_at))
            if meta["status"] in ("rejected", "needs_information"):
                out[("note", log.entity_id)] = log.created_at
        elif "public_note" in (meta.get("fields") or []):
            out[("note", log.entity_id)] = log.created_at
    return out


def _timeline(path, status, created_at, events, language, fallback_at=None):
    """Stages along ``path`` with the date each was first reached."""
    reached = {path[0]: created_at}
    for state, at in events:
        reached.setdefault(state, at)
    if status in CLOSED_STEPS:
        path = [step for step in path if step in reached and step != status] + [status]
    elif status not in path:
        path = path[:1] + [status] + path[1:]
    current = path.index(status) if status in path else 0
    steps = []
    for index, step in enumerate(path):
        at = reached.get(step) if index <= current else None
        if index == current and at is None:
            at = fallback_at
        ar, en = STEP_LABELS.get(step, (step, step))
        steps.append({
            "key": step,
            "label": ar if language == "ar" else en,
            "at": at,
            "done": index <= current,
            "current": index == current,
            "closed": step in CLOSED_STEPS,
        })
    return steps


def _registration_view(row, language, history):
    item = platform_tracking._registration_item(row, language, True)
    path = ["submitted", "under_review", "approved", "provisioned"]
    if row.status == "needs_information":
        path = ["submitted", "under_review", "needs_information", "approved", "provisioned"]
    events = history.get(("registration", str(row.pk)), [])
    item.update({
        "timeline": _timeline(path, row.status, row.created_at, events, language,
                              fallback_at=row.reviewed_at or row.updated_at),
        "note": item.pop("reason", ""),
        "note_updated_at": None,
        "plan": _plan_name(row),
    })
    if item["note"]:
        item["note_updated_at"] = history.get(("note", str(row.pk))) or row.reviewed_at
    return item


def _plan_name(row):
    try:
        return row.plan_version.plan.name if row.plan_version_id else ""
    except Exception:  # noqa: BLE001
        return ""


def _demo_view(row, language, history):
    item = platform_tracking._demo_item(row, language, True)
    events = list(history.get(("demo", str(row.pk)), []))
    if row.last_contacted_at:
        events.append(("contacted", row.last_contacted_at))
        events.sort(key=lambda event: event[1])
    item.update({
        "customer": row.name,
        "timeline": _timeline(["new", "contacted", "qualified"], row.status, row.created_at,
                              events, language, fallback_at=row.updated_at),
        "note": item.pop("reason", ""),
        "note_updated_at": None,
    })
    return item
