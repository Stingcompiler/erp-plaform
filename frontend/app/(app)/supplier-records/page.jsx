"use client";

import { purchasing } from "@/lib/api";
import PartyRecords from "@/components/records/PartyRecords";

// Gated to the `purchasing` module — the same RBAC the dashboards use. The
// server enforces it independently on /api/suppliers/{id}/records/.
export default function SupplierRecordsPage() {
  return (
    <PartyRecords
      kind="supplier"
      module="purchasing"
      fetchList={purchasing.suppliers}
      fetchRecords={purchasing.supplierRecords}
      csvUrl={purchasing.supplierRecordsCsv}
      titleKey="records.supplierTitle"
      subtitleKey="records.supplierSubtitle"
      selectKey="records.selectSupplier"
      createdKey="records.createdSupplier"
      noAccessKey="purchasing.noAccess"
      typeOptions={[
        "purchase_order",
        "goods_receipt",
        "bill",
        "payment",
        "return",
        "debit_note",
        "data_change",
      ]}
    />
  );
}
