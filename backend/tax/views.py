from decimal import Decimal, InvalidOperation

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
from core.rbac import RoleModuleAccess
from tax.handlers import REGISTRY, available_handlers, get_handler


class TaxProfileView(APIView):
    """
    GET/PATCH the caller's company TaxProfile. Gated to the `settings` module.
    Switching `invoice_format` between registered handlers changes both tax
    computation and invoice rendering with no other changes (Rule #7).
    """

    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "settings"

    def _profile(self, request):
        from org.models import Company
        company_id = getattr(request.user, "company_id", None)
        if company_id is None:
            return None
        company = Company.objects.select_related("tax_profile").get(pk=company_id)
        return company.tax_profile

    def _serialize(self, profile):
        return {
            "country": profile.country,
            "invoice_format": profile.invoice_format,
            "flat_tax_rate": str(profile.flat_tax_rate),
            "e_invoicing_enabled": profile.e_invoicing_enabled,
        }

    def get(self, request):
        profile = self._profile(request)
        if profile is None:
            return Response(
                {"detail": "A company-scoped user is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self._serialize(profile))

    def patch(self, request):
        profile = self._profile(request)
        if profile is None:
            return Response(
                {"detail": "A company-scoped user is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        fmt = request.data.get("invoice_format")
        if fmt is not None:
            if fmt not in REGISTRY:
                return Response(
                    {"detail": f"Unknown invoice_format '{fmt}'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            profile.invoice_format = fmt
        before = {
            "country": profile.country, "invoice_format": profile.invoice_format,
            "flat_tax_rate": str(profile.flat_tax_rate),
            "e_invoicing_enabled": profile.e_invoicing_enabled,
        }
        if "country" in request.data:
            country = str(request.data["country"] or "").strip().upper()
            if len(country) != 2 or not country.isalpha():
                return Response(
                    {"country": "Use a two-letter ISO 3166-1 country code."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            profile.country = country
        if "e_invoicing_enabled" in request.data:
            profile.e_invoicing_enabled = bool(request.data["e_invoicing_enabled"])
        if "flat_tax_rate" in request.data:
            try:
                rate = Decimal(str(request.data["flat_tax_rate"]))
            except (InvalidOperation, TypeError):
                return Response(
                    {"detail": "flat_tax_rate must be a number."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # A typo of 150 would inflate every subsequent invoice by 150%.
            if not get_handler(profile).validate_rate(rate):
                return Response(
                    {"flat_tax_rate": "The rate must be between 0 and 100 percent."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            profile.flat_tax_rate = rate
        profile.save()
        after = {
            "country": profile.country, "invoice_format": profile.invoice_format,
            "flat_tax_rate": str(profile.flat_tax_rate),
            "e_invoicing_enabled": profile.e_invoicing_enabled,
        }
        log_activity(
            action="update", request=request, entity_type="TaxProfile",
            entity_id=profile.id,
            metadata={"changes": {
                k: {"before": before[k], "after": after[k]}
                for k in before if before[k] != after[k]
            }},
        )
        return Response(self._serialize(profile))


class TaxHandlersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(available_handlers())


class InvoiceDocumentView(APIView):
    """
    GET /api/invoices/<id>/document/ — render an invoice through its company's
    tax handler. Same Invoice, different output depending on the company's
    invoice_format (Rule #7). Gated to the `sales` module (read).
    """

    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "sales"

    def get(self, request, invoice_id):
        from sales.models import Invoice
        company_id = getattr(request.user, "company_id", None)
        is_platform = getattr(request.user, "is_platform_admin", False)
        qs = Invoice.objects.select_related(
            "company__tax_profile", "customer", "branch", "created_by"
        ).prefetch_related("lines__product", "payments")
        if not is_platform:
            qs = qs.filter(company_id=company_id)
        try:
            invoice = qs.get(pk=invoice_id)
        except Invoice.DoesNotExist:
            return Response(
                {"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND
            )
        profile = getattr(invoice.company, "tax_profile", None)
        handler = get_handler(profile)
        return Response(handler.render(invoice))
