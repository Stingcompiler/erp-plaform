"""``/api/whatsapp/webhook/``: Meta's verification handshake and event delivery.

Unauthenticated by design (Meta has no session); trust comes from the
verify token on GET and the HMAC signature on POST. Always answers fast:
the body is stored and parsed inline (no worker on this deployment) and
nothing here calls out to Meta.
"""
import json
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from whatsapp.webhook import process, signature_is_valid

logger = logging.getLogger(__name__)
MAX_BODY = 1 << 20  # Meta bodies are a few KB; a megabyte is already abuse.


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook(request):
    if request.method == "GET":
        expected = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "")
        if (
            expected
            and request.GET.get("hub.mode") == "subscribe"
            and request.GET.get("hub.verify_token") == expected
            and request.GET.get("hub.challenge")
        ):
            return HttpResponse(request.GET["hub.challenge"], content_type="text/plain")
        return HttpResponse("Verification failed", status=403, content_type="text/plain")

    raw = request.body
    if len(raw) > MAX_BODY:
        return JsonResponse({"detail": "Too large."}, status=413)
    if not signature_is_valid(raw, request.headers.get("X-Hub-Signature-256", "")):
        logger.warning("WhatsApp webhook: bad or missing signature")
        return JsonResponse({"detail": "Invalid signature."}, status=403)
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError):
        return JsonResponse({"detail": "Malformed JSON."}, status=400)
    expected_objects = (None, "whatsapp_business_account")
    if not isinstance(payload, dict) or payload.get("object") not in expected_objects:
        return JsonResponse({"detail": "Unexpected object."}, status=400)
    try:
        counts = process(payload)
    except Exception:  # noqa: BLE001 - a parse bug must not make Meta retry forever
        logger.exception("WhatsApp webhook: failed to process body")
        counts = {"error": True}
    return JsonResponse({"status": "EVENT_RECEIVED", **counts})
