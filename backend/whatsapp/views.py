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


# ---------------------------------------------------------------------------
# Company settings: connect a number, choose templates, send a test.
# ---------------------------------------------------------------------------
from rest_framework import status as drf_status  # noqa: E402
from rest_framework.permissions import IsAuthenticated  # noqa: E402
from rest_framework.response import Response  # noqa: E402
from rest_framework.views import APIView  # noqa: E402

from core.activity import log_activity  # noqa: E402
from core.rbac import RoleModuleAccess, can_approve_high_value  # noqa: E402
from whatsapp import client  # noqa: E402
from whatsapp.models import (  # noqa: E402
    WhatsAppAccount,
    WhatsAppMessage,
    WhatsAppTemplate,
    digits_only,
)

RECENT = 20


def _company(request):
    company_id = getattr(request.user, "company_id", None)
    if company_id is None or getattr(request.user, "is_platform_admin", False):
        return None
    return request.user.company


def _account_payload(account):
    if account is None:
        return None
    return {
        "phone_number_id": account.phone_number_id,
        "waba_id": account.waba_id,
        "display_phone": account.display_phone,
        "display_name": account.display_name,
        "has_token": bool(account.access_token),
        "is_active": account.is_active,
        "last_event_at": account.last_event_at,
    }


def _message_payload(row):
    return {
        "id": row.pk, "direction": row.direction, "phone": row.phone,
        "contact_name": row.contact_name, "text": row.text, "status": row.status,
        "error_title": row.error_title, "purpose": (row.raw or {}).get("purpose", ""),
        "created_at": row.created_at,
    }


class WhatsAppSettingsView(APIView):
    """GET the company's WhatsApp connection, templates and recent traffic;
    PUT (manager/owner) updates the connection and template choices. The
    access token is write-only: it is never echoed back."""

    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "settings"

    def get(self, request):
        company = _company(request)
        if company is None:
            return Response({"detail": "A company user is required."}, status=400)
        account = WhatsAppAccount.objects.filter(company=company).first()
        chosen = {t.purpose: t for t in WhatsAppTemplate.objects.filter(company=company)}
        return Response({
            "account": _account_payload(account),
            "templates": [
                {
                    "purpose": key, "label": label,
                    "params": WhatsAppTemplate.PARAMS.get(key, []),
                    "template_name": chosen[key].template_name if key in chosen else "",
                    "language": chosen[key].language if key in chosen else "ar",
                    "is_active": chosen[key].is_active if key in chosen else True,
                }
                for key, label in WhatsAppTemplate.PURPOSES
            ],
            "recent_messages": [
                _message_payload(m)
                for m in WhatsAppMessage.objects.filter(company=company)[:RECENT]
            ],
            "opted_in_customers": company.customers.filter(whatsapp_opt_in=True).count(),
        })

    def put(self, request):
        company = _company(request)
        if company is None:
            return Response({"detail": "A company user is required."}, status=400)
        if not can_approve_high_value(request.user):
            return Response(
                {"detail": "Only a manager or owner may change the WhatsApp connection."},
                status=drf_status.HTTP_403_FORBIDDEN,
            )
        data = request.data or {}
        changed = []
        account_data = data.get("account")
        if isinstance(account_data, dict):
            phone_number_id = str(account_data.get("phone_number_id") or "").strip()
            if not phone_number_id:
                return Response({"account": "phone_number_id is required."}, status=400)
            clash = WhatsAppAccount.objects.filter(phone_number_id=phone_number_id).exclude(
                company=company
            ).exists()
            if clash:
                return Response(
                    {"account": "That phone number id is connected to another company."},
                    status=400,
                )
            account = WhatsAppAccount.objects.filter(company=company).first()
            if account is None:
                account = WhatsAppAccount(company=company, phone_number_id=phone_number_id)
            account.phone_number_id = phone_number_id
            account.waba_id = str(account_data.get("waba_id") or "").strip()[:32]
            account.display_phone = digits_only(account_data.get("display_phone"))[:32]
            account.display_name = str(account_data.get("display_name") or "").strip()[:120]
            account.is_active = bool(account_data.get("is_active", True))
            token = str(account_data.get("access_token") or "").strip()
            if token:
                account.access_token = token[:512]
            account.save()
            changed.append("account")
        templates = data.get("templates")
        if isinstance(templates, list):
            valid = dict(WhatsAppTemplate.PURPOSES)
            for item in templates:
                purpose = str((item or {}).get("purpose") or "")
                if purpose not in valid:
                    continue
                WhatsAppTemplate.objects.update_or_create(
                    company=company, purpose=purpose,
                    defaults={
                        "template_name": str(item.get("template_name") or "").strip()[:120],
                        "language": (str(item.get("language") or "ar").strip() or "ar")[:8],
                        "is_active": bool(item.get("is_active", True)),
                    },
                )
            changed.append("templates")
        if changed:
            log_activity(
                action="update", request=request, entity_type="WhatsAppAccount",
                entity_id=company.pk, metadata={"fields": changed},
            )
        return self.get(request)


class WhatsAppTestSendView(APIView):
    """Send one free-text message to prove the token works. Only reaches a
    number that wrote to the business in the last 24 hours (Meta's rule);
    the response says so when it did not."""

    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "settings"

    def post(self, request):
        company = _company(request)
        if company is None:
            return Response({"detail": "A company user is required."}, status=400)
        if not can_approve_high_value(request.user):
            return Response({"detail": "Manager or owner only."}, status=403)
        from whatsapp.notify import account_for

        account = account_for(company)
        if account is None:
            return Response({"detail": "Connect a number with an access token first."}, status=400)
        phone = digits_only(request.data.get("phone"))
        text = str(request.data.get("text") or "").strip()[:1000]
        if len(phone) < 8 or not text:
            return Response({"detail": "Enter a phone number and a message."}, status=400)
        row = client.send(
            account, phone, client.text_payload(phone, text), purpose="test", text=text,
        )
        return Response(_message_payload(row) if row else {"detail": "Not sent."})
