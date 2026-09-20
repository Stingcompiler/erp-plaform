import uuid

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


def branch_scope_for(user, branch_field):
    """The branch id a branch-scoped user is confined to, else None."""
    if not branch_field:
        return None
    role = getattr(user, "role", None)
    if not (role and role.scope_level == "branch"):
        return None
    return getattr(user, "branch_id", None)


def apply_branch_scope(qs, user, branch_field, include_unassigned=True):
    """Narrow ``qs`` to the user's branch exactly as the normal endpoint
    does. Shared by the viewsets and by sync/pull, so a mirror handed to an
    offline device can never show more than the screen would."""
    branch_id = branch_scope_for(user, branch_field)
    if branch_id is None:
        return qs
    own_branch = Q(**{f"{branch_field}_id": branch_id})
    if include_unassigned:
        return qs.filter(own_branch | Q(**{f"{branch_field}__isnull": True}))
    return qs.filter(own_branch)


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
        return branch_scope_for(self.request.user, self.branch_field)

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
        return apply_branch_scope(
            qs, self.request.user, self.branch_field, self.include_unassigned_branch_rows
        )

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


# Field names whose values must never be written to the audit trail. A
# password arrives in validated_data as plaintext and sits on the instance as
# a hash; either one in ActivityLog.metadata would hand every audit viewer a
# credential to crack. Matched case-insensitively as a suffix, so
# `new_password`, `api_token` and `client_secret` are covered too.
SENSITIVE_FIELD_SUFFIXES = ("password", "token", "secret", "signature")


def is_sensitive_field(name):
    lowered = str(name).lower()
    return any(lowered.endswith(suffix) for suffix in SENSITIVE_FIELD_SUFFIXES)


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
            write_only = {
                name
                for name, field in getattr(serializer, "fields", {}).items()
                if getattr(field, "write_only", False)
            }
            tracked = [
                f
                for f in (getattr(serializer, "validated_data", {}) or {})
                if f not in write_only and not is_sensitive_field(f)
            ]
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


def valid_client_uuid(value):
    """The client-supplied idempotency key, or None when absent or malformed.

    A malformed key used to reach the ORM lookup and raise ValueError — a
    500 for a typo. Treating it as absent lets the serializer refuse it
    with a proper 400 (client_uuid is a UUIDField there).
    """
    if not value:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None


class IdempotentCreateMixin:
    """
    Makes create replay-safe (PROJECT_RULES Rule #2). A client-supplied
    `client_uuid` that has already been recorded returns the existing row
    (200) instead of applying the action again — so a queued offline action
    re-sent after reconnect never double-applies. Shared by inventory (stock
    movements) and sales (payments, POS checkout).
    """

    def create(self, request, *args, **kwargs):
        client_uuid = valid_client_uuid(request.data.get("client_uuid"))
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
