from decimal import Decimal, InvalidOperation

from core.activity import log_activity
from core.rbac import can_approve_high_value
from core.deletion import ArchiveOnDeleteMixin
from core.permissions import EntitlementAccess, IsPlatformAdminOrReadOnly
from core.timezone import is_valid_timezone
from core.rbac import RoleModuleAccess
from core.scoping import (
    ActivityLoggingMixin,
    CompanyScopedModelViewSet,
)
from org.models import Branch, Company, Department, StoreModeAccessException
from org.store_mode import STORE_DEFAULT_ROLE_NAMES, is_system_mode_owner
from org.serializers import (
    BranchSerializer,
    CompanySerializer,
    DepartmentSerializer,
)
from rest_framework import status, viewsets
from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from subscriptions.services import assert_capacity


class CompanyViewSet(ActivityLoggingMixin, viewsets.ModelViewSet):
    """
    Company is the tenant root, so it can't scope by a `company` FK to itself.
    Instead: platform admins see/manage all companies; a normal user sees only
    the single company they belong to (by primary key), and cannot reach any
    other company's record even by guessing its ID.
    """

    serializer_class = CompanySerializer
    activity_entity_type = "Company"
    permission_classes = [IsPlatformAdminOrReadOnly]
    queryset = Company.objects.select_related("tax_profile").all()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_platform_admin", False):
            return qs
        company_id = getattr(user, "company_id", None)
        if company_id is None:
            return qs.none()
        return qs.filter(pk=company_id)


class CompanyProfileView(APIView):
    """
    GET/PATCH the caller's own company identity — the block printed at the top
    of every invoice, credit note and payment voucher.

    Separate from CompanyViewSet on purpose. That viewset guards the tenant
    root (creating companies, deactivating them, the slug) and is rightly
    platform-admin-only. But a business's own address and tax registration
    number are its own data, and needing a platform administrator to correct a
    typo in the address printed on every invoice would be absurd. So this view
    exposes exactly the issuer fields, gated on the `settings` module, and
    always resolves the company from the request user — never from the body.
    """

    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "settings"

    EDITABLE = [
        "name",
        "legal_name",
        "address",
        "phone",
        "email",
        "tax_number",
        "registration_number",
        "currency",
        "timezone",
        "business_type",
        "payment_approval_threshold",
        "stock_adjustment_approval_threshold",
        "default_payment_terms_days",
    ]

    def _company(self, request):
        company_id = getattr(request.user, "company_id", None)
        if company_id is None:
            return None
        return Company.objects.filter(pk=company_id).first()

    def _serialize(self, company):
        data = {f: getattr(company, f) for f in self.EDITABLE}
        data["id"] = company.id
        # Read-only: set implicitly by choosing a type, never posted directly,
        # so a client cannot dismiss the question without answering it.
        data["business_type_chosen"] = company.business_type_chosen
        return data

    def get(self, request):
        company = self._company(request)
        if company is None:
            return Response(
                {"detail": "A company-scoped user is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self._serialize(company))

    def patch(self, request):
        company = self._company(request)
        if company is None:
            return Response(
                {"detail": "A company-scoped user is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        changed = []
        if "business_type" in request.data and not is_system_mode_owner(request.user):
            return Response(
                {"detail": "Only the Business Owner may change the operating mode."},
                status=status.HTTP_403_FORBIDDEN,
            )
        for field in self.EDITABLE:
            if field in request.data:
                value = request.data[field]
                # `name` anchors the company everywhere; blanking it would
                # leave every document without an issuer.
                if field == "name" and not str(value).strip():
                    return Response(
                        {"detail": "Company name cannot be empty."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if field == "business_type" and value not in dict(Company.BUSINESS_TYPE_CHOICES):
                    return Response(
                        {"business_type": "Unknown business type."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if field.endswith("_threshold"):
                    if not can_approve_high_value(request.user):
                        return Response(
                            {field: "Only a manager or owner may set approval thresholds."},
                            status=status.HTTP_403_FORBIDDEN,
                        )
                    try:
                        value = Decimal(str(value))
                    except (InvalidOperation, TypeError, ValueError):
                        return Response({field: "Must be a number."}, status=400)
                    if value < 0:
                        return Response({field: "Cannot be negative."}, status=400)
                if field == "default_payment_terms_days":
                    try:
                        value = int(value)
                    except (TypeError, ValueError):
                        return Response({field: "Must be a whole number of days."}, status=400)
                    if value < 0 or value > 365:
                        return Response({field: "Must be between 0 and 365 days."}, status=400)
                if field == "timezone" and not is_valid_timezone(value):
                    return Response(
                        {
                            "timezone": (
                                "Unknown time zone; use an IANA name such as Africa/Khartoum."
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                setattr(company, field, value)
                changed.append(field)
                # Answering the question — even by re-picking the value it
                # already had — is what settles it. The prompt then stops.
                if field == "business_type" and not company.business_type_chosen:
                    company.business_type_chosen = True
                    changed.append("business_type_chosen")
        if changed:
            company.save(update_fields=changed)
            log_activity(
                action="update",
                request=request,
                entity_type="Company",
                entity_id=company.id,
                metadata={"fields": changed},
            )
        return Response(self._serialize(company))


class StoreModeSettingsView(APIView):
    """Owner-only configuration for company/shop switching and exemptions."""

    permission_classes = [IsAuthenticated, EntitlementAccess]

    def _company(self, request):
        if not is_system_mode_owner(request.user):
            return None
        return Company.objects.filter(pk=request.user.company_id).first()

    def _serialize(self, company):
        rules = StoreModeAccessException.objects.filter(company=company)
        return {
            "business_type": company.business_type,
            "default_allowed_roles": sorted(STORE_DEFAULT_ROLE_NAMES),
            "additional_user_ids": list(
                rules.filter(user__isnull=False).values_list("user_id", flat=True)
            ),
            "additional_role_ids": list(
                rules.filter(role__isnull=False).values_list("role_id", flat=True)
            ),
        }

    def get(self, request):
        company = self._company(request)
        if company is None:
            return Response(
                {"detail": "Only the Business Owner may manage operating mode."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(self._serialize(company))

    def patch(self, request):
        company = self._company(request)
        if company is None:
            return Response(
                {"detail": "Only the Business Owner may manage operating mode."},
                status=status.HTTP_403_FORBIDDEN,
            )
        user_ids = request.data.get("additional_user_ids", [])
        role_ids = request.data.get("additional_role_ids", [])
        if not isinstance(user_ids, list) or not isinstance(role_ids, list):
            return Response(
                {"detail": "Exception lists must be arrays."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from accounts.models import Role, User

        users = User.objects.filter(company=company, id__in=user_ids)
        roles = Role.objects.filter(id__in=role_ids)
        if users.count() != len(set(user_ids)) or roles.count() != len(set(role_ids)):
            return Response(
                {"detail": "An exception must refer to a company user or known role."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        StoreModeAccessException.objects.filter(company=company).delete()
        StoreModeAccessException.objects.bulk_create(
            [
                *[StoreModeAccessException(company=company, user=user) for user in users],
                *[StoreModeAccessException(company=company, role=role) for role in roles],
            ]
        )
        log_activity(
            action="update",
            request=request,
            entity_type="Company",
            entity_id=company.id,
            metadata={
                "store_mode_exception_users": len(user_ids),
                "store_mode_exception_roles": len(role_ids),
            },
        )
        return Response(self._serialize(company))


class BranchViewSet(ArchiveOnDeleteMixin, CompanyScopedModelViewSet):
    """Archived, not deleted: warehouses, employees, invoices and users are all
    placed in the org tree by branch, and branch-scoped visibility depends on
    that placement resolving."""

    capacity_resource = "branches"

    queryset = Branch.objects.select_related("company").all()
    serializer_class = BranchSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        if self.request.user.company_id is None:
            return super().perform_create(serializer)
        company = Company.objects.select_for_update().get(pk=self.request.user.company_id)
        assert_capacity(company, "branches")
        super().perform_create(serializer)

    activity_entity_type = "Branch"

    def get_queryset(self):
        qs = super().get_queryset()
        role = getattr(self.request.user, "role", None)
        if role and role.name == "Branch Manager":
            return qs.filter(pk=self.request.user.branch_id)
        return qs

    def create(self, request, *args, **kwargs):
        if getattr(getattr(request.user, "role", None), "name", None) == "Branch Manager":
            return Response(
                {"detail": "A Branch Manager cannot create another branch."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if getattr(getattr(request.user, "role", None), "name", None) == "Branch Manager":
            return Response(
                {"detail": "A Branch Manager cannot archive a branch."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)


class DepartmentViewSet(CompanyScopedModelViewSet):
    queryset = Department.objects.select_related("company", "branch").all()
    serializer_class = DepartmentSerializer
    activity_entity_type = "Department"
    # Departments are maintained by HR; this lets an HR manager organise the
    # workforce without granting access to company-wide settings.
    rbac_module = "hr"
