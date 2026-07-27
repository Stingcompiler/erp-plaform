from core.activity import log_activity
from core.deletion import ArchiveOnDeleteMixin
from core.permissions import IsPlatformAdminOrReadOnly
from core.rbac import RoleModuleAccess
from core.scoping import (
    ActivityLoggingMixin,
    CompanyScopedModelViewSet,
)
from org.models import Branch, Company, Department
from org.serializers import (
    BranchSerializer,
    CompanySerializer,
    DepartmentSerializer,
)
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


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
        "name", "legal_name", "address", "phone", "email",
        "tax_number", "registration_number", "currency", "business_type",
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
                if field == "business_type" and value not in dict(
                    Company.BUSINESS_TYPE_CHOICES
                ):
                    return Response(
                        {"business_type": "Unknown business type."},
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
                action="update", request=request, entity_type="Company",
                entity_id=company.id, metadata={"fields": changed},
            )
        return Response(self._serialize(company))


class BranchViewSet(ArchiveOnDeleteMixin, CompanyScopedModelViewSet):
    """Archived, not deleted: warehouses, employees, invoices and users are all
    placed in the org tree by branch, and branch-scoped visibility depends on
    that placement resolving."""

    queryset = Branch.objects.select_related("company").all()
    serializer_class = BranchSerializer
    activity_entity_type = "Branch"


class DepartmentViewSet(CompanyScopedModelViewSet):
    queryset = Department.objects.select_related("company", "branch").all()
    serializer_class = DepartmentSerializer
    activity_entity_type = "Department"
