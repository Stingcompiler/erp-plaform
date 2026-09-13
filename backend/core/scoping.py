from django.db import IntegrityError
from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from core.activity import log_activity
from core.deletion import ManagerOnlyDeleteMixin


def assert_user_branch(user, obj, field_name):
    """Reject a related object outside a branch-scoped user's branch."""
    role = getattr(user, "role", None)
    if not role or role.scope_level != "branch" or obj is None:
        return
    if getattr(obj, "branch_id", None) != getattr(user, "branch_id", None):
        raise ValidationError(
            {field_name: "This record is outside your assigned branch."}
        )


class CompanyScopedQuerySetMixin:
    """
    Enforces PROJECT_RULES Rule #1: no endpoint returns cross-company data.

    Every company-owned model is filtered to the requesting user's company in
    `get_queryset`, and `company` is forced from the user on create — never
    trusted from the request body. Because retrieve/update/delete all resolve
    the object through this filtered queryset, guessing another company's
    object ID yields a 404, not another tenant's row.

    We enforce here in a shared base class (which PROJECT_RULES Rule #1
    explicitly permits as an alternative to middleware) rather than in Django
    middleware, because DRF runs authentication inside the view — so
    `request.user` is not yet resolved at Django-middleware time. Inheriting
    this base is mandatory for every company-owned viewset from M1 onward.
    """

    # Set on subclasses if the FK to Company isn't literally named "company".
    company_field = "company"

    # Opt-in row-level branch visibility. This may be a direct branch FK or a
    # relation path such as ``employee__branch``. Direct fields are stamped on
    # create; relation paths are validated by their serializers.
    branch_field = None
    include_unassigned_branch_rows = True

    def _user_company_id(self):
        user = self.request.user
        return getattr(user, "company_id", None)

    def _branch_scope(self):
        """Return the branch id to scope to, or None if no branch scoping applies."""
        if not self.branch_field:
            return None
        user = self.request.user
        role = getattr(user, "role", None)
        if not (role and role.scope_level == "branch"):
            return None
        return getattr(user, "branch_id", None)

    def is_platform_user(self):
        """Super Administrators are platform-level and not company-scoped."""
        user = self.request.user
        return bool(getattr(user, "is_platform_admin", False))

    def get_queryset(self):
        qs = super().get_queryset()
        if self.is_platform_user():
            return qs.none()
        company_id = self._user_company_id()
        if company_id is None:
            # Authenticated but company-less non-platform user sees nothing.
            return qs.none()
        qs = qs.filter(**{f"{self.company_field}_id": company_id})
        branch_id = self._branch_scope()
        if branch_id is not None:
            own_branch = Q(**{f"{self.branch_field}_id": branch_id})
            if self.include_unassigned_branch_rows:
                qs = qs.filter(
                    own_branch | Q(**{f"{self.branch_field}__isnull": True})
                )
            else:
                qs = qs.filter(own_branch)
        return qs

    def perform_create(self, serializer):
        if self.is_platform_user():
            raise PermissionDenied(
                "Platform accounts cannot create tenant business records."
            )
        kwargs = {self.company_field + "_id": self._user_company_id()}
        branch_id = self._branch_scope()
        if branch_id is not None and "__" not in self.branch_field:
            kwargs[self.branch_field + "_id"] = branch_id
        serializer.save(**kwargs)


class ActivityLoggingMixin:
    """Logs create/update/delete to the ActivityLog (Rule #8) for a viewset."""

    activity_entity_type = None  # e.g. "Company"; defaults to model name.

    def _entity_type(self):
        if self.activity_entity_type:
            return self.activity_entity_type
        return self.get_serializer().Meta.model.__name__

    def perform_create(self, serializer):
        super().perform_create(serializer)
        log_activity(
            action="create",
            request=self.request,
            entity_type=self._entity_type(),
            entity_id=serializer.instance.pk,
        )

    def _capture_changes(self, serializer):
        """Best-effort before/after snapshot of the fields being updated, for
        the audit trail. Never raises — auditing must not break the write."""
        try:
            tracked = list(getattr(serializer, "validated_data", {}) or {})
            instance = serializer.instance
            before = {f: str(getattr(instance, f, "")) for f in tracked}
            return before, tracked
        except Exception:
            return {}, []

    def perform_update(self, serializer):
        before, tracked = self._capture_changes(serializer)
        super().perform_update(serializer)
        changes = {}
        try:
            inst = serializer.instance
            for f in tracked:
                after = str(getattr(inst, f, ""))
                if before.get(f) != after:
                    changes[f] = {"before": before.get(f), "after": after}
        except Exception:
            changes = {}
        log_activity(
            action="update",
            request=self.request,
            metadata={"changes": changes} if changes else None,
            entity_type=self._entity_type(),
            entity_id=serializer.instance.pk,
        )

    def perform_destroy(self, instance):
        pk = instance.pk
        super().perform_destroy(instance)
        log_activity(
            action="delete",
            request=self.request,
            entity_type=self._entity_type(),
            entity_id=pk,
        )


class CompanyScopedModelViewSet(
    ManagerOnlyDeleteMixin,
    ActivityLoggingMixin,
    CompanyScopedQuerySetMixin,
    viewsets.ModelViewSet,
):
    """
    Base for every company-owned CRUD endpoint from M1 onward. Combines
    company scoping (Rule #1) with audit logging (Rule #8) so neither can be
    forgotten per-view. MRO note: ActivityLoggingMixin wraps
    CompanyScopedQuerySetMixin.perform_create, so company is assigned before
    the create is logged.

    Deletion defaults to tier C (see core/deletion.py): a hard delete that only
    a manager-level role may perform. Module write access alone is not enough,
    because "may record sales" should not imply "may erase a customer".
    Viewsets whose rows carry financial weight override this with
    NoDeleteMixin; master data that history points at uses ArchiveOnDeleteMixin.
    """

    pass


class IdempotentCreateMixin:
    """
    Makes create replay-safe (PROJECT_RULES Rule #2). A client-supplied
    `client_uuid` that has already been recorded returns the existing row
    (200) instead of applying the action again — so a queued offline action
    re-sent after reconnect never double-applies. Shared by inventory (stock
    movements) and sales (payments, POS checkout).
    """

    def create(self, request, *args, **kwargs):
        client_uuid = request.data.get("client_uuid")
        if client_uuid:
            existing = self.get_queryset().filter(client_uuid=client_uuid).first()
            if existing:
                return Response(
                    self.get_serializer(existing).data, status=status.HTTP_200_OK
                )
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError:
            if client_uuid:
                existing = self.get_queryset().filter(client_uuid=client_uuid).first()
                if existing:
                    return Response(
                        self.get_serializer(existing).data, status=status.HTTP_200_OK
                    )
            raise


class AppendOnlyScopedViewSet(
    IdempotentCreateMixin,
    ActivityLoggingMixin,
    CompanyScopedQuerySetMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    List/retrieve/create only — no update or destroy — enforcing append-only
    audit/financial/stock records (Rule #9) at the API surface, with company
    scoping (Rule #1), audit logging (Rule #8), and idempotency (Rule #2).
    """

    pass
