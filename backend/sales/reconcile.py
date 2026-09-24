"""Match a bank-app statement against recorded transfers.

The customer shows a Bankak/Fawri/O-Cash screenshot at the till and the
cashier records the transfer. Later the owner exports the app's statement
and wants to know: which recorded transfers really arrived, which arrived
that nobody recorded, and which were recorded but never came. This module
answers that from an .xlsx/.csv export and, on apply, marks the confirmed
payments verified — the same control as the manual verify action, with the
statement as the second pair of eyes.
"""
import re
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from core.party_import import _norm_header, _rows_from_csv, _rows_from_xlsx

MAX_ROWS = 5000
HEADERS = {
    "reference": {
        "reference", "ref", "ref no", "ref.", "reference no", "reference number",
        "transaction id", "transaction", "txn id", "txn", "trx id", "trx",
        "رقم العملية", "رقم المرجع", "المرجع", "مرجع", "رقم الحوالة", "رقم الإشعار",
        "رقم المعاملة", "رقم التحويل", "المعاملة",
    },
    "amount": {
        "amount", "credit", "credit amount", "amount credited", "value",
        "المبلغ", "دائن", "القيمة", "مبلغ", "وارد",
    },
    "date": {
        "date", "time", "date time", "datetime", "التاريخ", "الوقت", "تاريخ", "التاريخ والوقت",
    },
    "sender": {"sender", "from", "name", "sender name", "المرسل", "الاسم", "من", "اسم المرسل"},
}


def _map_headers(headers):
    mapping = {}
    for index, raw in enumerate(headers):
        key = _norm_header(raw)
        for field, spellings in HEADERS.items():
            if key in spellings and field not in mapping:
                mapping[field] = index
                break
    missing = [f for f in ("reference", "amount") if f not in mapping]
    if missing:
        raise ValidationError({"file": [
            _("The first row must name the columns; a reference and an amount "
              "column are required.")
        ]})
    return mapping


def _amount(value):
    text = re.sub(r"[^\d.\-]", "", str(value or "").replace("،", "").replace(",", ""))
    if not text:
        return None
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def parse_statement(uploaded):
    """Yield (row_number, {reference, amount, date, sender}) per data row."""
    name = (getattr(uploaded, "name", "") or "").lower()
    data = uploaded.read()
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        rows = _rows_from_xlsx(data)
    elif name.endswith(".csv") or name.endswith(".txt") or not name:
        rows = _rows_from_csv(data)
    else:
        raise ValidationError({"file": [_("Upload an .xlsx or .csv file.")]})
    rows = iter(rows)
    try:
        headers = next(rows)
    except StopIteration:
        raise ValidationError({"file": [_("The file is empty.")]})
    mapping = _map_headers(headers)
    count = 0
    for number, row in enumerate(rows, start=2):
        if not any(str(v).strip() for v in row):
            continue
        count += 1
        if count > MAX_ROWS:
            raise ValidationError({"file": [_("At most %(n)s rows per file.") % {"n": MAX_ROWS}]})
        record = {}
        for field, index in mapping.items():
            value = row[index] if index < len(row) else ""
            record[field] = str(value).strip() if value is not None else ""
        yield number, record


def _payment_row(payment):
    return {
        "id": payment.pk,
        "invoice_number": payment.invoice.number,
        "customer": getattr(payment.invoice.customer, "name", "") or "",
        "amount": payment.amount,
        "recorded_at": payment.recorded_at,
        "recorded_by": getattr(payment.recorded_by, "email", "") or "",
        "sender_bank_name": payment.sender_bank_name,
        "transfer_reference": payment.transfer_reference,
        "reference_last4": payment.reference_last4,
        "verified": payment.verified_at is not None,
    }


DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y")
# A transfer is recorded a few days either side of the bank's value date.
DATE_SLACK_DAYS = 5


def _date(value):
    from datetime import datetime

    text = str(value or "").strip()[:10]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def reconcile(company, account, uploaded, user, *, dry_run):
    """Match statement rows to this account's transfers; apply marks verified.

    Match order per row: the full reference; then (last 4 digits + amount)
    only against payments recorded without a full reference, and only when
    that pair is unique. Rows and payments are consumed once.
    """
    from datetime import timedelta

    from core.rbac import can_approve_high_value
    from core.scoping import apply_branch_scope
    from sales.models import Payment
    from sales.serializers import normalise_reference

    if account.company_id != company.pk:
        raise ValidationError({"account": [_("Unknown account.")]})
    # The same branch walls as the payments list: a branch user reconciled
    # (and saw) every branch's transfers.
    payments = list(
        apply_branch_scope(
            Payment.objects.filter(
                company=company, company_bank_account=account, method=Payment.BANK_TRANSFER,
            ),
            user, "invoice__branch", include_unassigned=False,
        ).select_related("invoice__customer", "recorded_by").order_by("recorded_at")
    )
    threshold = getattr(company, "payment_approval_threshold", 0) or 0
    approver = can_approve_high_value(user)
    statement_days = []
    by_reference = {}
    by_last4_amount = {}
    for payment in payments:
        if payment.transfer_reference:
            # A payment that carries the app's full id is matched on that id
            # only. Falling back to last-4 + amount here let statement row
            # BBB1234 verify payment AAA1234 (review F10).
            by_reference.setdefault(payment.transfer_reference, []).append(payment)
        elif payment.reference_last4:
            by_last4_amount.setdefault(
                (payment.reference_last4, payment.amount), []
            ).append(payment)

    taken = set()
    matched, unmatched_rows = [], []
    rows = 0
    for number, record in parse_statement(uploaded):
        rows += 1
        reference = normalise_reference(record.get("reference"))
        amount = _amount(record.get("amount"))
        day = _date(record.get("date"))
        if day:
            statement_days.append(day)
        row = {
            "row": number, "reference": reference, "amount": amount,
            "date": record.get("date", ""), "sender": record.get("sender", ""),
        }
        if not reference or amount is None:
            unmatched_rows.append({**row, "reason": "unreadable"})
            continue
        candidates = [p for p in by_reference.get(reference, []) if p.pk not in taken]
        how = "reference"
        if not candidates:
            digits = re.sub(r"\D", "", reference)
            candidates = [
                p for p in by_last4_amount.get((digits[-4:], amount), []) if p.pk not in taken
                # Last-4 + amount is weak evidence: only a payment recorded
                # around this row's date (an old row verified a newer,
                # unrelated payment with the same digits and amount).
                and (day is None or abs((timezone.localdate(p.recorded_at) - day).days)
                     <= DATE_SLACK_DAYS)
            ] if digits else []
            how = "last4_amount"
            if len(candidates) > 1:
                unmatched_rows.append({**row, "reason": "ambiguous"})
                continue
        if not candidates:
            unmatched_rows.append({**row, "reason": "not_recorded"})
            continue
        payment = candidates[0]
        # One transfer settling several invoices is stored as one payment per
        # invoice sharing a receipt_group: the statement row is their sum.
        # Comparing it to the first payment alone never matched.
        group = [
            p for p in candidates
            if payment.receipt_group and p.receipt_group == payment.receipt_group
        ] or [payment]
        taken.update(p.pk for p in group)
        total = sum((p.amount for p in group), Decimal("0"))
        matched.append({
            **row, "how": how, "payment": _payment_row(payment),
            "payments": [_payment_row(p) for p in group],
            "group_total": total,
            "amount_differs": total != amount,
        })

    # Unverified transfers are listed as "not on this statement" only when
    # they fall in its period; otherwise every old one showed up each time.
    if statement_days:
        first = min(statement_days) - timedelta(days=DATE_SLACK_DAYS)
        last = max(statement_days) + timedelta(days=DATE_SLACK_DAYS)
        in_period = lambda p: first <= timezone.localdate(p.recorded_at) <= last  # noqa: E731
    else:
        in_period = lambda p: True  # noqa: E731
    unmatched_payments = [
        _payment_row(p) for p in payments
        if p.pk not in taken and p.verified_at is None and in_period(p)
    ]

    applied = skipped_self = already = 0
    if not dry_run:
        now = timezone.now()
        with transaction.atomic():
            for item in matched:
                # Re-read under a lock: two uploads of overlapping statements
                # must not both verify (and count) the same transfer.
                group = list(
                    Payment.objects.select_for_update()
                    .filter(pk__in=[p["id"] for p in item["payments"]]).order_by("pk")
                )
                if all(p.verified_at is not None for p in group):
                    already += 1
                    item["outcome"] = "already_verified"
                    continue
                if item["amount_differs"]:
                    item["outcome"] = "amount_differs"
                    continue
                if any(p.recorded_by_id and p.recorded_by_id == user.id for p in group):
                    skipped_self += 1
                    item["outcome"] = "self_recorded"
                    continue
                # The manual verify refuses these for non-approvers; an upload
                # verified them anyway.
                if threshold and item["group_total"] >= threshold and not approver:
                    item["outcome"] = "needs_approver"
                    continue
                for payment in group:
                    if payment.verified_at is None:
                        payment.verified_at = now
                        payment.verified_by = user
                        payment.save(update_fields=["verified_at", "verified_by"])
                applied += 1
                item["outcome"] = "verified"
    return {
        "dry_run": dry_run, "account": account.pk, "rows": rows,
        "matched": matched, "unmatched_rows": unmatched_rows,
        "unmatched_payments": unmatched_payments,
        "applied": applied, "skipped_self": skipped_self, "already_verified": already,
    }
