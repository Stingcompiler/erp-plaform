"""
Shared "360° record" builder for customer and supplier pages.

Both pages answer the same question — *everything that ever happened with this
party* — so the timeline assembly, filtering, ordering and CSV export live here
once. Each caller supplies its own typed event sources; this module normalises
them into one chronological stream (most recent first).

Company scoping is the caller's responsibility: every source queryset is already
narrowed by the viewset's CompanyScopedQuerySetMixin, so nothing here can widen
it. Filtering is applied *after* assembly because the stream is heterogeneous.
"""
from decimal import Decimal

from core.csvexport import csv_download, rows_download
from core.models import ActivityLog


def event(kind, label, date, ref="", amount=None, meta="", entity_id=None):
    """One normalised timeline row. `entity_id` is the row behind it when a
    printable document exists for it (invoice, payment, credit note…)."""
    return {
        "type": kind,
        "label": label,
        # ISO for stable client-side sorting/formatting; None dates are dropped.
        "date": date.isoformat() if date else None,
        "reference": str(ref or ""),
        "amount": str(amount) if amount is not None else None,
        "meta": meta or "",
        "entity_id": entity_id,
    }


def data_change_events(company_id, entity_type, entity_id):
    """Audit-log rows for this record — the 'changes to their data' history.

    Deliberately excludes `view` / `export`: those are access events, not data
    changes, and surfacing them here would make the timeline grow every time
    someone merely opened the page. They remain visible on the Audit Logs page.
    """
    logs = (
        ActivityLog.objects.filter(
            company_id=company_id, entity_type=entity_type, entity_id=str(entity_id)
        )
        .exclude(action__in=["view", "export"])
        .select_related("user")
    )
    out = []
    for log in logs:
        changed = ", ".join((log.metadata or {}).get("changes", {}).keys())
        out.append(
            event(
                "data_change",
                log.action,
                log.created_at,
                ref=log.entity_id,
                meta=f"{log.user.email if log.user else 'system'}"
                + (f" · {changed}" if changed else ""),
            )
        )
    return out


def assemble(events, params):
    """Filter + sort the combined stream. Newest first."""
    kind = params.get("type")
    if kind:
        events = [e for e in events if e["type"] == kind]

    start, end = params.get("start"), params.get("end")
    if start:
        events = [e for e in events if e["date"] and e["date"][:10] >= start]
    if end:
        events = [e for e in events if e["date"] and e["date"][:10] <= end]

    search = (params.get("search") or "").strip().lower()
    if search:
        events = [
            e
            for e in events
            if search in e["label"].lower()
            or search in e["reference"].lower()
            or search in e["meta"].lower()
            or search in e["type"].lower()
        ]

    # Undated rows sort last rather than crashing the comparison.
    return sorted(events, key=lambda e: e["date"] or "", reverse=True)


def csv_response(party, events, filename):
    """Excel-compatible CSV export of the assembled timeline."""
    resp, writer = csv_download(filename)
    writer.writerow([party.get("name", ""), party.get("status", "")])
    writer.writerow([])
    writer.writerow(["Date", "Type", "Description", "Reference", "Amount", "Details"])
    for e in events:
        writer.writerow(
            [
                (e["date"] or "")[:19].replace("T", " "),
                e["type"],
                e["label"],
                e["reference"],
                e["amount"] or "",
                e["meta"],
            ]
        )
    return resp


def money(value):
    return Decimal(value or 0)


def rows_csv(filename, header, rows):
    """
    Generic list export: a header row plus pre-formatted rows.

    Separate from `csv_response`, which exports an assembled party timeline with
    its own preamble. This one is for exporting a plain list — invoices,
    products — where the caller has already decided the columns.

    A BOM is written first so Excel opens Arabic text as UTF-8 instead of
    mangling it into Latin-1; without it every exported Arabic name arrives as
    unreadable characters. Cells a spreadsheet would run as formulas are
    neutralised (see core.csvexport).
    """
    return rows_download(filename, header, rows)
