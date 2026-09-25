// Comparison pages. Only comparisons whose every cell can be verified from
// the product itself belong here; a page against a named competitor needs
// the Vezano team to check that competitor's current facts first.
//
// Shape per language: title, metaTitle, description, lead, columns
// [label, label, label], rows [[criterion, col1, col2, col3]], verdict
// (array of paragraphs), cta. A cell that is `true`/`false` renders as a
// check or a dash; a string renders as text.

export const COMPARISONS = [
  {
    slug: "excel-and-paper",
    ar: {
      title: "فيزانو مقابل إكسل والدفاتر الورقية",
      metaTitle: "فيزانو مقابل إكسل والدفاتر الورقية — متى يكفي الجدول ومتى يلزم نظام",
      description:
        "مقارنة صريحة بين إدارة المحل بالدفاتر وجداول إكسل وبين نظام فيزانو: أين يكفي الجدول، وأين تبدأ الخسارة الصامتة في المخزون والديون والفروع.",
      lead:
        "الدفتر وجدول إكسل ليسا خطأ. معظم المحلات الناجحة بدأت بهما، وكثير منها يستمر بهما لسنوات. المقارنة أدناه ليست عن أيهما أفضل مطلقًا، بل عن اللحظة التي يتحول فيها الجدول من أداة إلى عبء.",
      columns: ["الدفتر الورقي", "جدول إكسل", "فيزانو"],
      rows: [
        ["البيع في الكاونتر", "يدوي وبطيء", "غير مناسب", "كاشير بالباركود والوزن والعبوة"],
        ["يعمل أثناء انقطاع الإنترنت", true, true, "نعم، مع مزامنة تلقائية بلا تكرار"],
        ["الرصيد الحالي للمخزون", "يُحسب يدويًا", "يُحدَّث يدويًا بعد كل بيع", "يُشتق تلقائيًا من كل حركة"],
        ["الدفعات وتواريخ الصلاحية", "بالذاكرة", "عمود إضافي دون تنبيه", "FEFO تلقائي وقائمة على اللوحة"],
        ["من يدين لك ومنذ متى", "ورقة لكل عميل", "جدول يُنسى تحديثه", "كشف حساب وأعمار ديون تلقائية"],
        ["أكثر من شخص يعمل في الوقت نفسه", false, "نسخ متضاربة", "صلاحيات لكل دور وفرع"],
        ["من غيّر ماذا ومتى", false, false, "سجل تدقيق كامل"],
        ["فرع ثانٍ", "دفتر ثانٍ", "ملف ثانٍ وجمع يدوي", "إعداد واحد، تقارير موحّدة"],
        ["النسخ الاحتياطي", "لا يوجد", "إن تذكّرت", "نسخة ليلية تلقائية للسجلات الأساسية على السحابة، أو سكربت على خادمك"],
        ["الوقت لإعداد التقرير الشهري", "ساعات", "ساعة أو أكثر", "لحظي، لأي فترة وأي فرع"],
        ["التكلفة الشهرية", "لا شيء", "لا شيء", "باقة شهرية أو رخصة دائمة"],
        ["الوقت لبدء العمل", "فوري", "فوري", "ظهيرة واحدة مع استيراد المنتجات"],
      ],
      verdict: [
        "يكفي الدفتر أو الجدول ما دام شخص واحد يبيع، والأصناف قليلة ولا صلاحية لها، والبيع نقدًا. في هذه الحالة النظام تكلفة بلا عائد.",
        "يبدأ الجدول في الخسارة الصامتة عند أول واحدة من ثلاث علامات: صنف انتهت صلاحيته على الرف ولم يلاحظه أحد، عميل اختُلف معه على رصيده ولا وثيقة تحسم الخلاف، أو موظف ثانٍ يحتاج أن يبيع في الوقت نفسه. عندها تكلفة النظام أقل من تكلفة الخطأ الواحد.",
        "فيزانو مصمّم للانتقال في ظهيرة واحدة: استورد منتجاتك من ملف إكسل نفسه، أدخل الرصيد الافتتاحي، وابدأ البيع. البيانات تبقى ملكك: تنزّل نسخك الاحتياطية من الإعدادات متى شئت، وفريقنا يصدّر الشركة كاملة عند الطلب.",
      ],
      cta: "استورد جدولك وابدأ التجربة",
    },
    en: {
      title: "Vezano versus Excel and paper ledgers",
      metaTitle: "Vezano versus Excel and paper ledgers — when a spreadsheet is enough and when a system is needed",
      description:
        "A frank comparison between running a shop on ledgers and spreadsheets and running it on Vezano: where the spreadsheet is enough, and where the silent losses in stock, debts and branches begin.",
      lead:
        "A ledger and an Excel sheet are not a mistake. Most successful shops started with them, and many carry on with them for years. The comparison below is not about which is better in the abstract, but about the moment the spreadsheet turns from a tool into a burden.",
      columns: ["Paper ledger", "Excel sheet", "Vezano"],
      rows: [
        ["Selling at the counter", "Manual and slow", "Not suitable", "Cashier with barcode, weight and packs"],
        ["Works during an internet outage", true, true, "Yes, with automatic sync and no duplicates"],
        ["Current stock balance", "Calculated by hand", "Updated by hand after every sale", "Derived automatically from every movement"],
        ["Batches and expiry dates", "From memory", "An extra column, no alert", "Automatic FEFO and a list on the dashboard"],
        ["Who owes you and since when", "A page per customer", "A sheet that goes stale", "Automatic statements and ageing"],
        ["More than one person working at once", false, "Conflicting copies", "Permissions per role and branch"],
        ["Who changed what and when", false, false, "A full audit log"],
        ["A second branch", "A second ledger", "A second file and manual totals", "One setting, consolidated reports"],
        ["Backups", "None", "If you remember", "An automatic nightly backup of core records in the cloud, or a script on your server"],
        ["Time to prepare the monthly report", "Hours", "An hour or more", "Instant, for any period and any branch"],
        ["Monthly cost", "Nothing", "Nothing", "A monthly plan or a perpetual licence"],
        ["Time to get started", "Immediate", "Immediate", "One afternoon, with products imported"],
      ],
      verdict: [
        "A ledger or a spreadsheet is enough as long as one person sells, the items are few and do not expire, and sales are cash. In that case a system is cost without return.",
        "The spreadsheet starts losing silently at the first of three signs: an item expires on the shelf and nobody noticed, a customer disputes their balance and no document settles it, or a second employee needs to sell at the same time. At that point the system costs less than a single mistake.",
        "Vezano is designed for a one-afternoon move: import your products from the same Excel file, enter opening stock, and start selling. The data remains yours: download your backups from Settings whenever you like, and our team exports the whole company on request.",
      ],
      cta: "Import your spreadsheet and start the trial",
    },
  },
];

export function comparison(slug) {
  return COMPARISONS.find((item) => item.slug === slug) || null;
}
