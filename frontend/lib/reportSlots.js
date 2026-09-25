// One report request's state, so each card on the reports page tells its own
// truth. The page used to count every refusal as "N reports failed" in one
// banner while the charts below said "no data for this period" — a failed
// load read as a quiet month.
//
//   loading   – asked, not answered yet
//   ok        – answered (possibly with nothing in it: see isEmptyReport)
//   error     – the request failed (network, server): retry makes sense
//   forbidden – the role may not read it (403): retrying cannot help
//   locked    – the plan does not include reports (403 module_not_in_plan)

export const LOADING = { status: "loading", data: null };

export function slotFromError(error) {
  const response = error?.response;
  if (response?.status === 403) {
    return response.data?.code === "module_not_in_plan" ? "locked" : "forbidden";
  }
  return "error";
}

// "No data for this period": an empty list, or an object whose rows/items
// are empty. A figure object (totals) is never "empty" — zero is an answer.
export function isEmptyReport(data) {
  if (data === null || data === undefined) return true;
  if (Array.isArray(data)) return data.length === 0;
  if (Array.isArray(data.rows)) return data.rows.length === 0;
  if (Array.isArray(data.items)) return data.items.length === 0;
  return false;
}

// Whether the signed-in company's plan includes a module. Unknown (an older
// cached session without the list) counts as included: the server decides.
export function planIncludes(entitlements, module) {
  const modules = entitlements?.modules;
  if (!Array.isArray(modules)) return true;
  return modules.includes("*") || modules.includes(module);
}
