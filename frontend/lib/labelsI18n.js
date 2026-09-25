// Words for stored codes (lib/labels.js) and for the per-card states the
// identity review asked for (2026-09-25): a report that failed says so on
// its own card, a plan without reports says that once, long worklists fold
// behind a count.

export const labelsEn = {
  invoiceStatus: {
    issued: "Unpaid",
    partially_paid: "Partly paid",
    paid: "Paid",
    void: "Void",
  },
  paymentMethod: {
    cash: "Cash",
    bank_transfer: "Bank transfer",
    credit: "Store credit",
  },
};

export const labelsAr = {
  invoiceStatus: {
    issued: "غير مسددة",
    partially_paid: "مسددة جزئيًا",
    paid: "مسددة",
    void: "ملغاة",
  },
  paymentMethod: {
    cash: "نقدًا",
    bank_transfer: "تحويل بنكي",
    credit: "رصيد متجر",
  },
};

export const statesEn = {
  reportFailed: "This report didn't load — the figures are missing, not zero.",
  reportForbidden: "Your role can't read this report.",
  reportNotInPlan: "Not included in your current plan.",
  reportsNotInPlanTitle: "Reports aren't in your current plan",
  reportsNotInPlanOwner: "Your plan covers the day-to-day screens but not the reports module. Change the plan from the Subscription page to add it.",
  reportsNotInPlanStaff: "The company's plan does not include the reports module. Ask the owner if you need it.",
  openSubscription: "Open subscription",
  noReportAreasTitle: "No reports for your role",
  noReportAreasBody: "Your role doesn't cover a report area. An administrator can change the role if you need one.",
  inventoryProductsTab: "Products",
  showList: "Show list",
  hideList: "Hide list",
  awaitingSummary: "{count} payment(s) waiting, {amount} in total. Open the list to verify them.",
  verifyLoadError: "Couldn't load the payments awaiting verification. Retry, or check the connection.",
};

export const statesAr = {
  reportFailed: "تعذّر تحميل هذا التقرير — الأرقام لم تصل، وليست أصفارًا.",
  reportForbidden: "دورك لا يسمح بقراءة هذا التقرير.",
  reportNotInPlan: "غير مشمول في باقتك الحالية.",
  reportsNotInPlanTitle: "التقارير غير مشمولة في باقتك الحالية",
  reportsNotInPlanOwner: "باقتك تغطي شاشات العمل اليومي دون وحدة التقارير. غيّر الباقة من صفحة الاشتراك لإضافتها.",
  reportsNotInPlanStaff: "باقة الشركة لا تشمل وحدة التقارير. اطلبها من المالك إن احتجت إليها.",
  openSubscription: "فتح الاشتراك",
  noReportAreasTitle: "لا توجد تقارير لدورك",
  noReportAreasBody: "دورك لا يغطي أي مجال تقارير. يمكن للمسؤول تعديل الدور إن احتجت إلى ذلك.",
  inventoryProductsTab: "المنتجات",
  showList: "عرض القائمة",
  hideList: "إخفاء القائمة",
  awaitingSummary: "{count} دفعة بالانتظار، مجموعها {amount}. افتح القائمة للتحقق منها.",
  verifyLoadError: "تعذّر تحميل الدفعات المنتظرة للتحقق. أعد المحاولة أو تحقّق من الاتصال.",
};
