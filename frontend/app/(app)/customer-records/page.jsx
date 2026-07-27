"use client";

import { sales } from "@/lib/api";
import PartyRecords from "@/components/records/PartyRecords";

// Gated to the `sales` module — the same RBAC the dashboards use. The server
// enforces it independently on /api/customers/{id}/records/.
export default function CustomerRecordsPage() {
  return (
    <PartyRecords
      kind="customer"
      module="sales"
      fetchList={sales.customers}
      fetchRecords={sales.customerRecords}
      csvUrl={sales.customerRecordsCsv}
      titleKey="records.customerTitle"
      subtitleKey="records.customerSubtitle"
      selectKey="records.selectCustomer"
      createdKey="records.created"
      noAccessKey="sales.noAccess"
      typeOptions={[
        "quotation",
        "order",
        "invoice",
        "payment",
        "return",
        "credit_note",
        "data_change",
      ]}
    />
  );
}
