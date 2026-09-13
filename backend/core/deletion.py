"""
Deletion policy (PROJECT_RULES Rule #9 — financial records are append-only).

Why deletion needs more care here than in a typical CRUD app: every balance in
this system is DERIVED, never stored. Stock is SUM(StockMovement.quantity); a
bank balance is opening + received - paid. In a system that stores balances,
removing a row leaves a mismatch that reconciliation will surface. Here it
simply produces a different, perfectly self-consistent, WRONG number — there is
no drift left behind to detect. The audit log records that a delete happened,
but no report will ever show a trace of it.

So deletion is graded into three tiers:

  A. Never deletable — anything carrying financial or stock effect.
     `NoDeleteMixin` answers 405 and names the correcting action instead.
     (Most tier-A models never had a delete route: they use
     `AppendOnlyScopedViewSet`. This mixin covers the ones that need ordinary
     edits but must not vanish, such as Expense.)
  B. Archivable — master data that history points at: products, customers,
     suppliers, users, warehouses. `ArchiveOnDeleteMixin` turns DELETE into
     `is_active = False`, so pickers hide the row while every past document
     still resolves to a real record.
  C. Hard delete — records with no financial effect. Permitted, audited, and
     restricted to a manager-level role by `ManagerOnlyDeleteMixin`, which
     `CompanyScopedModelViewSet` applies by default.

A note on the 405/403 bodies: each one says what to do *instead*. A dead end
with no way forward is exactly what pushes users to go delete the row straight
from the Django admin, bypassing every control in this module.
"""

from rest_framework import status
from django.db import transaction
from rest_framework.decorators import action
from rest_framework.response import Response

from core.activity import log_activity
from core.rbac import can_delete


class ManagerOnlyDeleteMixin:
    """Tier C: hard delete allowed, but only for a manager-level role."""

    # Set False where removing a row is ordinary editing rather than a
    # supervisory act — landing-page sections, CRM notes, a mistyped attendance
    # line. Those carry no financial weight, and gating them would block the
    # very role that owns the work (a Website Manager is not a "manager" in the
    # RBAC sense and would otherwise be unable to delete their own draft
    # sections).
    manager_only_delete = True

    def destroy(self, request, *args, **kwargs):
        if self.manager_only_delete and not can_delete(request.user):
            return Response(
                {
                    "detail": (
                        "Your role can edit this record but not delete it. "
                        "Ask a manager to remove it if that is really needed."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)


class NoDeleteMixin:
    """Tier A: the record can never be removed, only corrected."""

    delete_denied_detail = (
        "This record is part of the financial trail and cannot be deleted. "
        "Record a correcting entry instead."
    )

    def destroy(self, request, *args, **kwargs):
        return Response(
            {"detail": self.delete_denied_detail},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class ArchiveOnDeleteMixin:
    """
    Tier B: DELETE archives the row instead of removing it.

    Reuses the `is_active` flag these models already carry, so this needs no
    migration and introduces no second notion of "deleted" competing with the
    existing active/inactive filters. Logged as `archive` rather than `delete`
    so the audit trail states what actually happened.

    Archiving is idempotent — archiving an already-archived row is a no-op that
    still returns 204, because a client retrying after a dropped response must
    not get an error for work that already succeeded.
    """

    archive_field = "is_active"
    capacity_resource = None

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        if self.capacity_resource:
            from org.models import Company
            from subscriptions.services import assert_capacity

            instance = self.get_object()
            company = Company.objects.select_for_update().get(pk=instance.company_id)
            instance.refresh_from_db()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            if not instance.is_active and serializer.validated_data.get("is_active") is True:
                assert_capacity(company, self.capacity_resource)
        return super().update(request, *args, **kwargs)

    # Archiving is reversible and destroys nothing, so it is ordinary work for
    # whoever owns the module — an inventory officer retiring a discontinued
    # product should not need a manager. Hard deletion stays manager-only; that
    # is the irreversible one.
    manager_only_delete = False

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def unarchive(self, request, pk=None):
        """Puts an archived row back into circulation.

        Without this, "archive instead of delete" is a one-way door and users
        learn to avoid it — which pushes them back towards wanting real deletes.
        """
        instance = self.get_object()
        if self.capacity_resource:
            from org.models import Company
            from subscriptions.services import assert_capacity

            company = Company.objects.select_for_update().get(pk=instance.company_id)
            instance.refresh_from_db()
            if not instance.is_active:
                serializer = self.get_serializer(instance, data={"is_active": True}, partial=True)
                serializer.is_valid(raise_exception=True)
                assert_capacity(company, self.capacity_resource)
        if not getattr(instance, self.archive_field, False):
            setattr(instance, self.archive_field, True)
            instance.save(update_fields=[self.archive_field])
            log_activity(
                action="unarchive",
                request=request,
                entity_type=self._entity_type(),
                entity_id=instance.pk,
            )
        return Response(self.get_serializer(instance).data)

    def perform_destroy(self, instance):
        # Deliberately not calling super(): ActivityLoggingMixin.perform_destroy
        # would delete the row and log a `delete` that never happened.
        if getattr(instance, self.archive_field, False):
            setattr(instance, self.archive_field, False)
            instance.save(update_fields=[self.archive_field])
            log_activity(
                action="archive",
                request=self.request,
                entity_type=self._entity_type(),
                entity_id=instance.pk,
            )
