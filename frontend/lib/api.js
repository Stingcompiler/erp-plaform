import axios from "axios";

// One axios instance for the whole app. withCredentials sends the HttpOnly
// auth cookie set by /api/auth/login/ on every request, and a 401 interceptor
// lets the auth layer react to an expired session.
const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api",
  withCredentials: true,
});

// The access cookie lives 30 minutes; the refresh cookie lives 7 days. Without
// this interceptor every session died silently mid-work at the 30-minute mark.
// On a 401 we refresh ONCE (a single shared promise so parallel failures don't
// stampede the endpoint) and replay the original request; only when the
// refresh itself fails is the session really over, and the caller's own error
// handling (AuthProvider) takes it from there. Auth endpoints are excluded so
// a wrong password or an expired refresh can't loop.
let refreshInFlight = null;
api.interceptors.response.use(null, async (error) => {
  const { config, response } = error;
  if (
    response?.status !== 401 ||
    !config ||
    config._retried ||
    String(config.url || "").includes("/auth/")
  ) {
    throw error;
  }
  refreshInFlight ||= api
    .post("/auth/refresh/")
    .finally(() => { refreshInFlight = null; });
  await refreshInFlight; // a failed refresh rejects: the original 401 stands
  return api({ ...config, _retried: true });
});

// Platform inboxes (subscriptions, payments, registrations) must show every
// row, not the first page: a pending payment on page 2 is still pending. This
// follows DRF's `next` links and resolves to a plain array, so callers keep
// working whether or not the endpoint paginates.
export async function listAll(path, params = {}, { maxPages = 40 } = {}) {
  const rows = [];
  let response = await api.get(path, { params });
  for (let page = 0; page < maxPages; page += 1) {
    const data = response.data;
    if (!Array.isArray(data?.results)) return { data: Array.isArray(data) ? data : rows };
    rows.push(...data.results);
    if (!data.next) break;
    response = await api.get(data.next);
  }
  return { data: rows };
}

// Endpoint helpers — named by what the user does, not by transport details.
export const auth = {
  login: (email, password) => api.post("/auth/login/", { email, password }),
  logout: () => api.post("/auth/logout/"),
  me: () => api.get("/auth/me/"),
};

export const rbac = {
  access: () => api.get("/rbac/access/"),
};

export const prefs = {
  get: () => api.get("/ops/preferences/"),
  update: (body) => api.patch("/ops/preferences/", body),
  languages: () => api.get("/ops/languages/"),
};

export const dashboard = {
  get: () => api.get("/dashboard/"),
};

// Attention badges: what appeared for this user since they last looked.
export const attention = {
  get: () => api.get("/attention/"),
  seen: (key) => api.post("/attention/seen/", { key }),
};

export const inventory = {
  uploadProductImage: (id, file) => {
    const form = new FormData();
    form.append("image", file);
    return api.post(`/products/${id}/image/`, form, { headers: { "Content-Type": "multipart/form-data" } });
  },
  removeProductImage: (id) => api.delete(`/products/${id}/image/`),
  products: (params) => api.get("/products/", { params }),
  lowStock: (params) => api.get("/products/low_stock/", { params }),
  negativeStock: (params) => api.get("/products/negative_stock/", { params }),
  expiringBatches: () => api.get("/products/expiring-batches/"),
  packs: (params) => api.get("/product-packs/", { params }),
  createPack: (body) => api.post("/product-packs/", body),
  updatePack: (id, body) => api.patch(`/product-packs/${id}/`, body),
  stockCounts: (params) => api.get("/stock-counts/", { params }),
  createStockCount: (body) => api.post("/stock-counts/", body),
  updateStockCount: (id, body) => api.patch(`/stock-counts/${id}/`, body),
  submitStockCount: (id) => api.post(`/stock-counts/${id}/submit/`),
  approveStockCount: (id) => api.post(`/stock-counts/${id}/approve/`),
  cancelStockCount: (id) => api.post(`/stock-counts/${id}/cancel/`),
  createProduct: (body) => api.post("/products/", body),
  updateProduct: (id, body) => api.patch(`/products/${id}/`, body),
  // DELETE archives (is_active=false) — the row and its stock history stay.
  archiveProduct: (id) => api.delete(`/products/${id}/`),
  unarchiveProduct: (id) => api.post(`/products/${id}/unarchive/`),
  productsCsv: (params) =>
    `${API_BASE}/products/export/?${new URLSearchParams(params || {})}`,
  stock: (id) => api.get(`/products/${id}/stock/`),
  // Exact-match scan lookup — resolves to one product or 404 (never fuzzy).
  byBarcode: (code) => api.get("/products/by-barcode/", { params: { code } }),
  generateBarcode: (id) => api.post(`/products/${id}/generate-barcode/`),
  movements: (productId) => api.get("/stock-movements/", { params: { product: productId } }),
  warehouses: () => api.get("/warehouses/"),
  createWarehouse: (body) => api.post("/warehouses/", body),
  updateWarehouse: (id, body) => api.patch(`/warehouses/${id}/`, body),
  categories: () => api.get("/categories/"),
  createCategory: (body) => api.post("/categories/", body),
  brands: () => api.get("/brands/"),
  createBrand: (body) => api.post("/brands/", body),
  units: () => api.get("/units/"),
  createUnit: (body) => api.post("/units/", body),
  createAdjustment: (body) => api.post("/stock-adjustments/", body),
  createTransfer: (body) => api.post("/stock-transfers/", body),
};

export const sales = {
  checkout: (body) => api.post("/pos/checkout/", body, { timeout: 15000 }),
  invoice: (id) => api.get(`/invoices/${id}/`),
  invoices: (params) => api.get("/invoices/", { params }),
  invoiceDocument: (id) => api.get(`/invoices/${id}/document/`),
  invoicesCsv: (params) => `${API_BASE}/invoices/export/?${new URLSearchParams(params || {})}`,
  payments: (params) => api.get("/payments/", { params }),
  paymentDocument: (id) => api.get(`/payments/${id}/document/`),
  customers: (params) => api.get("/customers/", { params }),
  debtCustomers: (params) => api.get("/debts/customers/", { params }),
  debtSummary: () => api.get("/debts/summary/"),
  debtStatement: (id, params) => api.get(`/customers/${id}/debt-statement/`, { params }),
  customerRecords: (id, params) => api.get(`/customers/${id}/records/`, { params }),
  customerRecordsCsv: (id, params) =>
    `${API_BASE}/customers/${id}/records/?${new URLSearchParams({ ...params, format: "csv" })}`,
};

export const cashShifts = {
  list: (params) => api.get("/cash-shifts/", { params }),
  // The caller's own open drawer, so the till resumes after a page reload.
  current: () => api.get("/cash-shifts/current/"),
  open: (body) => api.post("/cash-shifts/", body),
  close: (id, body) => api.post(`/cash-shifts/${id}/close/`, body),
  review: (id) => api.post(`/cash-shifts/${id}/review/`),
  movements: (shiftId) => api.get("/drawer-movements/", { params: { shift: shiftId } }),
  addMovement: (body) => api.post("/drawer-movements/", body),
};

export const bankAccounts = {
  list: () => api.get("/bank-accounts/"),
  create: (body) => api.post("/bank-accounts/", body),
  update: (id, body) => api.patch(`/bank-accounts/${id}/`, body),
};

export const reports = {
  hrSummary: (params) => api.get("/reports/hr-summary/", { params }),
  payroll: (params) => api.get("/reports/payroll/", { params }),
  incomeStatement: (params) => api.get("/reports/income-statement/", { params }),
  cashFlow: (params) => api.get("/reports/cash-flow/", { params }),
  receivablesDue: (params) => api.get("/reports/receivables-due/", { params }),
  payablesDue: (params) => api.get("/reports/payables-due/", { params }),
  cfoKpis: (params) => api.get("/reports/cfo-kpis/", { params }),
  salesSummary: (params) => api.get("/reports/sales-summary/", { params }),
  salesByProduct: (params) => api.get("/reports/sales-by-product/", { params }),
  inventoryValuation: (params) => api.get("/reports/inventory-valuation/", { params }),
  arAging: () => api.get("/reports/ar-aging/"),
  profitSummary: (params) => api.get("/reports/profit-summary/", { params }),
};

export const purchasing = {
  suppliers: (params) => api.get("/suppliers/", { params }),
  createSupplier: (body) => api.post("/suppliers/", body),
  supplierRecords: (id, params) => api.get(`/suppliers/${id}/records/`, { params }),
  supplierRecordsCsv: (id, params) =>
    `${API_BASE}/suppliers/${id}/records/?${new URLSearchParams({ ...params, format: "csv" })}`,
  receive: (body) => api.post("/receivings/", body),
  goodsReceipts: (params) => api.get("/goods-receipts/", { params }),
  bills: (params) => api.get("/bills/", { params }),
  createBill: (body) => api.post("/bills/", body),
  createSupplierPayment: (body) => api.post("/supplier-payments/", body),
  supplierPayments: (params) => api.get("/supplier-payments/", { params }),
  supplierPaymentDocument: (id) => api.get(`/supplier-payments/${id}/document/`),
};

export const returns = {
  salesReturns: (params) => api.get("/sales-returns/", { params }),
  createSalesReturn: (body) => api.post("/sales-returns/", body),
  disposition: (id, decisions) =>
    api.post(`/sales-returns/${id}/disposition/`, { decisions }),
  // Only the warehouses the disposition call will actually accept, so the UI
  // can't offer a choice that fails on submit.
  restockWarehouses: () => api.get("/sales-returns/restock_warehouses/"),
  purchaseReturns: (params) => api.get("/purchase-returns/", { params }),
  createPurchaseReturn: (body) => api.post("/purchase-returns/", body),
  creditNotes: (params) => api.get("/credit-notes/", { params }),
  creditNoteDocument: (id) => api.get(`/credit-notes/${id}/document/`),
  debitNotes: (params) => api.get("/debit-notes/", { params }),
  debitNoteDocument: (id) => api.get(`/debit-notes/${id}/document/`),
};

export const crm = {
  leads: (params) => api.get("/leads/", { params }),
  createLead: (body) => api.post("/leads/", body),
  updateLead: (id, body) => api.patch(`/leads/${id}/`, body),
  pipeline: (params) => api.get("/leads/pipeline/", { params }),
  // Won lead -> customer. Idempotent server-side.
  convertLead: (id) => api.post(`/leads/${id}/convert/`),
  groups: () => api.get("/customer-groups/"),
  createGroup: (body) => api.post("/customer-groups/", body),
  followups: (params) => api.get("/followups/", { params }),
  createFollowup: (body) => api.post("/followups/", body),
  updateFollowup: (id, body) => api.patch(`/followups/${id}/`, body),
  notes: (params) => api.get("/crm-notes/", { params }),
  createNote: (body) => api.post("/crm-notes/", body),
};

export const hr = {
  leaveAccrualPolicies: () => api.get("/leave-accrual-policies/"),
  createLeaveAccrualPolicy: (body) => api.post("/leave-accrual-policies/", body),
  updateLeaveAccrualPolicy: (id, body) => api.patch(`/leave-accrual-policies/${id}/`, body),
  generateLeaveAllowances: (year) => api.post("/leave-accrual-policies/generate/", { year }),
  leaveAllowances: (params) => api.get("/leave-allowances/", { params }),
  createLeaveAllowance: (body) => api.post("/leave-allowances/", body),
  updateLeaveAllowance: (id, body) => api.patch(`/leave-allowances/${id}/`, body),
  employees: (params) => api.get("/employees/", { params }),
  createEmployee: (body) => api.post("/employees/", body),
  updateEmployee: (id, body) => api.patch(`/employees/${id}/`, body),
  positions: () => api.get("/positions/"),
  createPosition: (body) => api.post("/positions/", body),
  updatePosition: (id, body) => api.patch(`/positions/${id}/`, body),
  leave: (params) => api.get("/leave-requests/", { params }),
  createLeave: (body) => api.post("/leave-requests/", body),
  // Sick-leave with a medical report is sent as multipart form data.
  createLeaveMultipart: (formData) =>
    api.post("/leave-requests/", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  reportUrl: (id) => `${API_BASE}/leave-requests/${id}/report/`,
  approveLeave: (id) => api.post(`/leave-requests/${id}/approve/`),
  rejectLeave: (id) => api.post(`/leave-requests/${id}/reject/`),
  cancelLeave: (id, reason) => api.post(`/leave-requests/${id}/cancel/`, { reason }),
  attendance: (params) => api.get("/attendance/", { params }),
  createAttendance: (body) => api.post("/attendance/", body),
  salaryAdvances: (params) => api.get("/salary-advances/", { params }),
  createSalaryAdvance: (body) => api.post("/salary-advances/", body),
  approveAdvance: (id) => api.post(`/salary-advances/${id}/approve/`),
  rejectAdvance: (id) => api.post(`/salary-advances/${id}/reject/`),
  payrollRuns: () => api.get("/payroll-runs/"),
  createPayrollRun: (period) => api.post("/payroll-runs/", { period }),
  refreshPayrollRun: (id) => api.post(`/payroll-runs/${id}/refresh/`),
  approvePayrollRun: (id) => api.post(`/payroll-runs/${id}/approve/`),
  policies: () => api.get("/work-policies/"),
  createPolicy: (body) => api.post("/work-policies/", body),
  deductions: (params) => api.get("/deductions/", { params }),
  createDeduction: (body) => api.post("/deductions/", body),
};

// Audit trail (System Logs). Server restricts to administrators — see
// core.permissions.IsAuditViewer.
export const logs = {
  list: (params) => api.get("/activity-logs/", { params }),
};

export const finance = {
  expenses: (params) => api.get("/expenses/", { params }),
  createExpense: (body) => api.post("/expenses/", body),
  summary: (params) => api.get("/expenses/summary/", { params }),
};

export const users = {
  list: (params) => api.get("/users/", { params }),
  get: (id) => api.get(`/users/${id}/`),
  create: (body) => api.post("/users/", body),
  update: (id, body) => api.patch(`/users/${id}/`, body),
  // DELETE archives (is_active=false) — attribution on payments stays intact.
  deactivate: (id) => api.delete(`/users/${id}/`),
  reactivate: (id) => api.patch(`/users/${id}/`, { is_active: true }),
  roles: () => api.get("/roles/"),
  branches: () => api.get("/branches/"),
};

export const website = {
  page: () => api.get("/website/page/"),
  updatePage: (body) => api.patch("/website/page/", body),
  publish: (publish) => api.post("/website/page/publish/", { publish }),
  sections: () => api.get("/website/sections/"),
  createSection: (body) => api.post("/website/sections/", body),
  updateSection: (id, body) => api.patch(`/website/sections/${id}/`, body),
  deleteSection: (id) => api.delete(`/website/sections/${id}/`),
  featured: () => api.get("/website/featured-products/"),
  createFeatured: (body) => api.post("/website/featured-products/", body),
  updateFeatured: (id, body) => api.patch(`/website/featured-products/${id}/`, body),
  deleteFeatured: (id) => api.delete(`/website/featured-products/${id}/`),
  // Images: the server validates, resizes and stores WebP; send the raw file.
  uploadImage: (kind, file) => {
    const form = new FormData();
    form.append("image", file);
    return api.post(`/website/page/image/${kind}/`, form, { headers: { "Content-Type": "multipart/form-data" } });
  },
  removeImage: (kind) => api.delete(`/website/page/image/${kind}/`),
  gallery: () => api.get("/website/gallery/"),
  addGalleryImage: (file, order = 0, caption = "") => {
    const form = new FormData();
    form.append("image", file);
    form.append("order", String(order));
    form.append("caption", caption);
    return api.post("/website/gallery/", form, { headers: { "Content-Type": "multipart/form-data" } });
  },
  updateGalleryImage: (id, body) => api.patch(`/website/gallery/${id}/`, body),
  deleteGalleryImage: (id) => api.delete(`/website/gallery/${id}/`),
  // The owner's draft rendered as the public page (HTML, for an iframe).
  previewUrl: () => `${api.defaults.baseURL}/website/page/preview/`,
};

export const settings = {
  taxProfile: () => api.get("/tax/profile/"),
  updateTaxProfile: (body) => api.patch("/tax/profile/", body),
  // The issuer identity printed on every document. Always resolves to the
  // caller's own company server-side — no id is passed or trusted.
  companyProfile: () => api.get("/company/profile/"),
  updateCompanyProfile: (body) => api.patch("/company/profile/", body),
  storeMode: () => api.get("/company/store-mode/"),
  updateStoreMode: (body) => api.patch("/company/store-mode/", body),
  taxHandlers: () => api.get("/tax/handlers/"),
  backups: () => api.get("/ops/backups/"),
  createBackup: () => api.post("/ops/backups/"),
};

export const sync = {
  push: (batch) => api.post("/sync/push/", batch),
  pull: (params) => api.get("/sync/pull/", { params }),
};

export const org = {
  branches: () => api.get("/branches/"),
  createBranch: (body) => api.post("/branches/", body),
  updateBranch: (id, body) => api.patch(`/branches/${id}/`, body),
  departments: () => api.get("/departments/"),
  createDepartment: (body) => api.post("/departments/", body),
  updateDepartment: (id, body) => api.patch(`/departments/${id}/`, body),
};

// Absolute API base, for links the browser navigates to directly (CSV export).
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api";

export default api;

export const demoRequests = { create: (body) => api.post("/public/demo-requests/", body) };

// Unauthenticated reads of the public company pages.
export const publicSite = {
  showcase: () => api.get("/public/showcase/"),
  contact: () => api.get("/public/site-contact/"),
};

export const registration = {
  overview: () => api.get("/platform/overview/"),
  publicPlans: () => api.get("/public/plans/"),
  create: (body) => api.post("/public/registration-requests/", body),
  list: (params) => listAll("/platform/registration-requests/", params),
  review: (id, body) => api.post(`/platform/registration-requests/${id}/review/`, body),
  approve: (id, body) => api.post(`/platform/registration-requests/${id}/approve/`, body),
  provision: (id) => api.post(`/platform/registration-requests/${id}/provision/`),
  reissueInvitation: (id) =>
    api.post(`/platform/registration-requests/${id}/reissue-invitation/`),
  setPlan: (id, planVersionId) =>
    api.patch(`/platform/registration-requests/${id}/`, { plan_version: planVersionId }),
  update: (id, body) => api.patch(`/platform/registration-requests/${id}/`, body),
  contact: (id, channel) =>
    api.post(`/platform/registration-requests/${id}/contact/`, { channel }),
  activateOwner: (token, password, kind = "owner") =>
    api.post(
      kind === "platform"
        ? "/public/platform-invitations/accept/"
        : "/public/owner-invitations/accept/",
      { token, password },
    ),
};

export const platformTeam = {
  list: () => listAll("/platform/team/"),
  get: (id) => api.get(`/platform/team/${id}/`),
  invite: (body) => api.post("/platform/team/", body),
  reissue: (id) => api.post(`/platform/team/${id}/reissue-invitation/`),
  deactivate: (id) => api.post(`/platform/team/${id}/deactivate/`),
  activate: (id) => api.post(`/platform/team/${id}/activate/`),
  roles: () => api.get("/platform/team/roles/"),
  setRole: (id, role) => api.post(`/platform/team/${id}/set-role/`, { role }),
  updateProfile: (id, body) => api.patch(`/platform/team/${id}/`, body),
  remove: (id) => api.delete(`/platform/team/${id}/`),
  activity: (params) => api.get("/platform/activity/", { params }),
  activityFacets: () => api.get("/platform/activity/facets/"),
};

// The SEO control page: site-wide settings (one row) and per-path overrides.
export const platformSeo = {
  settings: () => api.get("/platform/seo/settings/"),
  updateSettings: (body) => api.patch("/platform/seo/settings/", body),
  uploadOgImage: (file) => {
    const form = new FormData();
    form.append("image", file);
    return api.post("/platform/seo/settings/image/", form, { headers: { "Content-Type": "multipart/form-data" } });
  },
  removeOgImage: () => api.delete("/platform/seo/settings/image/"),
  overrides: () => api.get("/platform/seo/overrides/"),
  createOverride: (body) => api.post("/platform/seo/overrides/", body),
  updateOverride: (id, body) => api.patch(`/platform/seo/overrides/${id}/`, body),
  deleteOverride: (id) => api.delete(`/platform/seo/overrides/${id}/`),
};

export const platformLeads = {
  list: (params) => listAll("/platform/leads/", params),
  update: (id, body) => api.patch(`/platform/leads/${id}/`, body),
  contact: (id, channel) => api.post(`/platform/leads/${id}/contact/`, { channel }),
};

export const subscription = {
  deployment: () => api.get("/deployment/"),
  company: () => api.get("/subscription/"),
  payments: () => api.get("/subscription/payments/"),
  submitPayment: (body) => api.post("/subscription/payments/", body),
  license: () => api.get("/license/"),
  importLicense: (body) => api.post("/license/", body),
};

export const platformSubscriptions = {
  list: (params) => listAll("/platform/subscriptions/", params),
  plans: () => listAll("/platform/plans/"),
  configure: (id, body) => api.post(`/platform/subscriptions/${id}/configure/`, body),
  transition: (id, status, reason = "") =>
    api.post(`/platform/subscriptions/${id}/transition/`, { status, reason }),
  payments: (params) => listAll("/platform/subscription-payments/", params),
  invoices: (params) => listAll("/platform/subscription-invoices/", params),
  createInvoice: (body) => api.post("/platform/subscription-invoices/", body),
  verifyPayment: (id, allocations) =>
    api.post(`/platform/subscription-payments/${id}/verify/`, { allocations }),
  rejectPayment: (id, reason) =>
    api.post(`/platform/subscription-payments/${id}/reject/`, { reason }),
  paymentProofUrl: (id) =>
    `${api.defaults.baseURL}/platform/subscription-payments/${id}/proof/`,
  createPlan: (body) => api.post("/platform/plans/", body),
  createPlanVersion: (body) => api.post("/platform/plan-versions/", body),
  updatePlan: (id, body) => api.patch(`/platform/plans/${id}/`, body),
};
