from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.db.models import Exists, F, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from core.activity import log_activity
from core.deletion import ArchiveOnDeleteMixin
from core.records import rows_csv
from core.scoping import (
    AppendOnlyScopedViewSet,
    CompanyScopedModelViewSet,
)
from inventory.barcodes import next_internal_barcode, scan_candidates
from inventory.models import (
    ProductPack,
    StockCount,
    Brand,
    Category,
    Product,
    StockAdjustment,
    StockBatch,
    StockMovement,
    StockTransfer,
    Unit,
    Warehouse,
)
from inventory.counts import approve_count, cancel_count, submit_count
from inventory.stock_scope import branch_movements, with_on_hand
from inventory.serializers import (
    ProductPackSerializer,
    StockCountSerializer,
    BrandSerializer,
    CategorySerializer,
    ProductSerializer,
    StockAdjustmentSerializer,
    StockBatchSerializer,
    StockMovementSerializer,
    StockTransferSerializer,
    UnitSerializer,
    WarehouseSerializer,
)
from org.models import Company
from subscriptions.services import assert_capacity


# Catalogue master data is archived rather than deleted: products, categories,
# brands, units and warehouses are all cited by stock movements and invoice
# lines that must keep resolving for history to stay readable.
class CategoryViewSet(ArchiveOnDeleteMixin, CompanyScopedModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    activity_entity_type = "Category"


class BrandViewSet(ArchiveOnDeleteMixin, CompanyScopedModelViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
    activity_entity_type = "Brand"


class UnitViewSet(ArchiveOnDeleteMixin, CompanyScopedModelViewSet):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer
    activity_entity_type = "Unit"


class WarehouseViewSet(ArchiveOnDeleteMixin, CompanyScopedModelViewSet):
    capacity_resource = "warehouses"
    branch_field = "branch"
    include_unassigned_branch_rows = False
    queryset = Warehouse.objects.select_related("branch").all()
    serializer_class = WarehouseSerializer
    activity_entity_type = "Warehouse"
    # Sales, purchasing and finance documents name a warehouse; the org page
    # lists them under branches. Reading names is not stock access.
    rbac_read_modules = ("sales", "purchasing", "finance", "org")

    @transaction.atomic
    def perform_create(self, serializer):
        if self.request.user.company_id is None:
            return super().perform_create(serializer)
        company = Company.objects.select_for_update().get(pk=self.request.user.company_id)
        assert_capacity(company, "warehouses")
        super().perform_create(serializer)


class StockBatchViewSet(CompanyScopedModelViewSet):
    queryset = StockBatch.objects.select_related("product").all()
    serializer_class = StockBatchSerializer
    activity_entity_type = "StockBatch"

    def get_queryset(self):
        # The count drawer asks for one product's lots (?product=<id>).
        queryset = super().get_queryset()
        product = self.request.query_params.get("product")
        if product and product.isdigit():
            queryset = queryset.filter(product_id=int(product))
        return queryset


def _current_rate(user):
    company_id = getattr(user, "company_id", None)
    if company_id is None:
        return None
    return (
        Company.objects.filter(pk=company_id)
        .values_list("exchange_rate", flat=True).first()
    )


class ProductViewSet(ArchiveOnDeleteMixin, CompanyScopedModelViewSet):
    serializer_class = ProductSerializer
    # The public-website editor picks featured products from the catalogue.
    rbac_read_modules = ("website",)
    activity_entity_type = "Product"
    queryset = Product.objects.select_related("category", "brand", "unit").all()
    filter_backends = [SearchFilter]
    # A carton's barcode finds its product too (DRF wraps the reverse lookup
    # in EXISTS, so the on-hand annotation is not multiplied by the join).
    search_fields = ["sku", "name", "barcode", "packs__barcode"]

    @action(detail=True, methods=["post", "delete"], url_path="image",
            parser_classes=[MultiPartParser, FormParser, JSONParser])
    def image(self, request, pk=None):
        """The photo shown when the product is featured on the public page.
        POST a multipart `image`; DELETE removes it. Stored as WebP under the
        public media subtree (website.images)."""
        from website.images import PHOTO_SIDE, clear_image, prepare_image, replace_image

        product = self.get_object()
        if request.method == "DELETE":
            clear_image(product, "image")
        else:
            replace_image(product, "image", prepare_image(request.FILES.get("image"), PHOTO_SIDE))
        log_activity(
            action="update", request=request, entity_type="Product", entity_id=product.pk,
            metadata={"image": "removed" if request.method == "DELETE" else "set"},
        )
        return Response(self.get_serializer(product).data)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Read from the row, not request.user.company: that relation may be
        # a cached instance from before today's rate was recorded.
        context["exchange_rate"] = _current_rate(self.request.user)
        return context

    @action(detail=False, methods=["post"])
    def reprice(self, request):
        """Bulk reprice the active catalogue by exchange rate or by percent.
        `dry_run=1` previews the effect without writing. Manager or owner
        only: this rewrites every shelf price in one request."""
        from core.rbac import can_approve_high_value
        from inventory.pricing import reprice

        if not can_approve_high_value(request.user):
            return Response(
                {"detail": _("Only a manager or owner may reprice the catalogue.")},
                status=status.HTTP_403_FORBIDDEN,
            )
        company = Company.objects.get(pk=request.user.company_id)
        result = reprice(company, request.data)
        if not result["dry_run"] and result["changed"]:
            log_activity(
                action="update", request=request, entity_type="Product", entity_id="bulk",
                metadata={
                    "reprice": {
                        k: (str(v) if v is not None else None)
                        for k, v in result.items() if k != "sample"
                    }
                },
            )
        return Response(result)

    def get_queryset(self):
        # on-hand is ALWAYS derived from the movement ledger — annotated here so
        # list/detail never rely on a stored (drift-prone) quantity field.
        # A branch-scoped user sees the stock of their own branch's
        # warehouses (the same figure their till's offline mirror holds), not
        # a company-wide total that hid a shortage on their shelves.
        qs = (
            with_on_hand(super().get_queryset(), self.request.user)
            # The soonest expiry among lots that still hold stock, so the
            # till can warn before ringing up an expired or expiring item.
            # One correlated subquery, not a query per row.
            .annotate(next_expiry=Subquery(
                StockBatch.objects.filter(product=OuterRef("pk"), expiry_date__isnull=False)
                .annotate(remaining=Coalesce(Sum("stock_movements__quantity"), Decimal("0")))
                .filter(remaining__gt=0)
                .order_by("expiry_date")
                .values("expiry_date")[:1]
            ))
        )
        # Archived products stay out of the way in listings but must remain
        # reachable — otherwise archiving is deletion with extra steps and
        # nobody can undo it. `?archived=1` shows only archived, `?archived=all`
        # shows both.
        #
        # Detail routes are never filtered: `unarchive` resolves its object
        # through this queryset, so hiding archived rows here would make the
        # one action that recovers them 404.
        if self.action not in ("list", "export"):
            return qs
        # The label printer asks only for things it can print: a product
        # with a barcode, or with an active pack that has one.
        if self.request.query_params.get("has_barcode") in ("1", "true"):
            qs = qs.filter(
                ~Q(barcode="")
                | Exists(ProductPack.objects.filter(
                    product=OuterRef("pk"), is_active=True,
                ).exclude(barcode=""))
            )
        archived = self.request.query_params.get("archived")
        if archived in ("1", "true"):
            return qs.filter(is_active=False)
        if archived == "all":
            return qs
        return qs.filter(is_active=True)

    @action(detail=False, methods=["get"])
    def export(self, request):
        """CSV of the product catalogue, through the same scoped and filtered
        queryset as the list — an export can never widen what the caller sees."""
        products = self.filter_queryset(self.get_queryset())
        log_activity(
            action="export",
            request=request,
            entity_type="Product",
            metadata={"count": products.count()},
        )
        return rows_csv(
            "products.csv",
            [
                "SKU",
                "Name",
                "Barcode",
                "Category",
                "Brand",
                "Unit",
                "On hand",
                "Reorder level",
                "Cost price",
                "Sale price",
                "Active",
            ],
            [
                [
                    p.sku,
                    p.name,
                    p.barcode,
                    p.category.name if p.category_id else "",
                    p.brand.name if p.brand_id else "",
                    p.unit.name if p.unit_id else "",
                    p.annotated_on_hand,
                    p.reorder_level,
                    p.cost_price,
                    p.sale_price,
                    "yes" if p.is_active else "no",
                ]
                for p in products
            ],
        )

    @action(detail=True, methods=["post"], url_path="generate-barcode")
    def generate_barcode(self, request, pk=None):
        """
        Assign an internally generated EAN-13 to a product that has no
        manufacturer barcode (local goods). Refuses to overwrite an existing
        barcode — re-labelling a product that is already scannable would orphan
        every label already printed for it.
        """
        product = self.get_object()
        if product.barcode:
            return Response(
                {"detail": _("This product already has a barcode."), "barcode": product.barcode},
                status=status.HTTP_400_BAD_REQUEST,
            )
        company_id = product.company_id
        product.barcode = next_internal_barcode(company_id)
        product.save(update_fields=["barcode"])
        log_activity(
            action="update",
            request=request,
            entity_type="Product",
            entity_id=product.pk,
            metadata={"changes": {"barcode": {"before": "", "after": product.barcode}}},
        )
        return Response(self.get_serializer(product).data)

    @action(detail=False, methods=["get"], url_path="by-barcode")
    def by_barcode(self, request):
        """
        Exact-match barcode lookup for scanners: GET ?code=<barcode>.

        Deliberately NOT the fuzzy `?search=` filter — a scan must resolve to
        exactly one product or fail loudly, otherwise the wrong item is sold and
        the wrong stock is deducted. Company-scoped like every other query, so a
        barcode from another tenant simply isn't found.
        """
        code = (request.query_params.get("code") or "").strip()
        if not code:
            return Response(
                {"detail": _("A barcode is required.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        product = pack = None
        for candidate in scan_candidates(code):
            # An archived product is no longer sold: a scan of its old label
            # must not ring it up (restore it first if it is back on sale).
            product = self.get_queryset().filter(barcode=candidate, is_active=True).first()
            if product is not None:
                break
            # A carton/strip barcode resolves to its product plus the pack,
            # so one scan rings up the whole pack.
            pack = (
                ProductPack.objects.filter(
                    company_id=getattr(request.user, "company_id", None),
                    barcode=candidate, is_active=True, product__is_active=True,
                )
                .select_related("product")
                .first()
            )
            if pack is not None:
                product = pack.product
                break
        if product is None:
            return Response(
                {"detail": _("No product matches this barcode."), "code": code},
                status=status.HTTP_404_NOT_FOUND,
            )
        data = self.get_serializer(product).data
        if pack is not None:
            data["scanned_pack"] = ProductPackSerializer(pack).data
        return Response(data)

    @action(detail=False, methods=["get"])
    def low_stock(self, request):
        # Non-stock lines (bags, delivery, the miscellaneous catch-all) sit at
        # zero on hand forever; listing them as "low" would bury the products
        # that genuinely need reordering.
        # Archived products are not reordered either.
        qs = self.get_queryset().filter(
            is_active=True, is_stock_tracked=True, annotated_on_hand__lte=F("reorder_level")
        )
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def negative_stock(self, request):
        """Products with a ledger balance below zero — the reconciliation
        worklist left by sales that went through against stale stock."""
        qs = self.get_queryset().filter(
            is_active=True, is_stock_tracked=True, annotated_on_hand__lt=0
        )
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="expiring-batches")
    def expiring_batches(self, request):
        """Lots with stock that expire within 30 days (or already have)."""
        from inventory.alerts import expiring_batches

        company_id = getattr(request.user, "company_id", None)
        rows = [
            {
                "batch": batch.pk,
                "product": batch.product_id,
                "sku": batch.product.sku,
                "name": batch.product.name,
                "lot_number": batch.lot_number,
                "expiry_date": batch.expiry_date.isoformat(),
                "remaining": str(batch.remaining),
                "expired": batch.expiry_date < timezone.now().date(),
            }
            for batch in expiring_batches(company_id)
        ]
        return Response({"count": len(rows), "results": rows})

    @action(detail=True, methods=["get"])
    def stock(self, request, pk=None):
        product = self.get_object()
        # Only the warehouses the caller may see: a branch user was shown
        # every other branch's shelves (and a total that included them).
        moves = branch_movements(
            product.company_id, request.user, product.stock_movements.all()
        )
        per_warehouse = list(
            moves.values("warehouse", "warehouse__name")
            .annotate(on_hand=Coalesce(Sum("quantity"), Decimal("0")))
            .order_by("warehouse__name")
        )
        lots = moves.exclude(batch__isnull=True)
        per_batch = list(
            lots.values("batch", "batch__lot_number", "batch__expiry_date")
            .annotate(on_hand=Coalesce(Sum("quantity"), Decimal("0")))
            .order_by("batch__expiry_date", "batch__lot_number")
        )
        # Lot x warehouse, so the adjust/transfer form can show what a lot
        # holds in the warehouse being drawn from.
        per_batch_warehouse = list(
            lots.values("batch", "warehouse")
            .annotate(on_hand=Coalesce(Sum("quantity"), Decimal("0")))
            .order_by("batch", "warehouse")
        )
        total = moves.aggregate(total=Coalesce(Sum("quantity"), Decimal("0")))["total"]
        return Response(
            {
                "product": product.id,
                "sku": product.sku,
                "track_batches": product.track_batches,
                "on_hand": total,
                "by_warehouse": per_warehouse,
                "by_batch": per_batch,
                "by_batch_warehouse": per_batch_warehouse,
            }
        )


class StockMovementViewSet(AppendOnlyScopedViewSet):
    branch_field = "warehouse__branch"
    include_unassigned_branch_rows = False
    queryset = StockMovement.objects.select_related("product", "warehouse", "batch").all()
    serializer_class = StockMovementSerializer
    activity_entity_type = "StockMovement"

    def get_queryset(self):
        qs = super().get_queryset()
        product = self.request.query_params.get("product")
        if product:
            qs = qs.filter(product_id=product)
        warehouse = self.request.query_params.get("warehouse")
        if warehouse:
            qs = qs.filter(warehouse_id=warehouse)
        return qs.order_by("-created_at")


class StockAdjustmentViewSet(AppendOnlyScopedViewSet):
    branch_field = "warehouse__branch"
    include_unassigned_branch_rows = False
    queryset = StockAdjustment.objects.select_related("product", "warehouse", "movement").all()
    serializer_class = StockAdjustmentSerializer
    activity_entity_type = "StockAdjustment"


class StockTransferViewSet(AppendOnlyScopedViewSet):
    branch_field = "source_warehouse__branch"
    include_unassigned_branch_rows = False
    queryset = StockTransfer.objects.select_related(
        "product", "source_warehouse", "dest_warehouse"
    ).all()
    serializer_class = StockTransferSerializer
    activity_entity_type = "StockTransfer"


class StockCountViewSet(CompanyScopedModelViewSet):
    """Periodic physical counts. Draft is editable; submit freezes ledger
    balances into the lines; approve (a manager other than the counter) posts
    the variances as adjustments. Approved counts are immutable."""

    branch_field = "warehouse__branch"
    include_unassigned_branch_rows = False
    queryset = StockCount.objects.select_related(
        "warehouse", "counted_by", "approved_by"
    ).prefetch_related("lines__product", "lines__batch")
    serializer_class = StockCountSerializer
    activity_entity_type = "StockCount"
    http_method_names = ["get", "post", "patch", "head", "options"]

    def _transition(self, request, service):
        count = self.get_object()
        result = service(count.pk, request.user, request)
        count = result[0] if isinstance(result, tuple) else result
        return Response(self.get_serializer(count).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self._transition(request, submit_count)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._transition(request, approve_count)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._transition(request, cancel_count)


class ProductPackViewSet(CompanyScopedModelViewSet):
    """Selling units per product (carton of 12, strip of 10, 5 kg sack)."""

    queryset = ProductPack.objects.select_related("product").all()
    serializer_class = ProductPackSerializer
    activity_entity_type = "ProductPack"
    filter_backends = [SearchFilter]
    search_fields = ["name", "barcode", "product__sku", "product__name"]

    def get_queryset(self):
        qs = super().get_queryset()
        product_id = self.request.query_params.get("product")
        return qs.filter(product_id=product_id) if product_id else qs
