// Solution pages: one per problem a merchant searches for, in both
// languages. Each page is a landing page for a long-tail query ("نقطة بيع
// تعمل بدون إنترنت", "offline POS") that the home page cannot rank for on its
// own. Facts here must match what the product does — see lib/marketingI18n.js
// (productAr/productEn) for the module descriptions they are drawn from.
//
// Shape per language: title (h1), metaTitle (<title>), description (meta and
// intro), lead, sections [{heading, body, bullets?}], faq [[q, a]], cta.

export const SOLUTIONS = [
  {
    slug: "multi-branch",
    shot: "dashboard",
    ar: {
      title: "نظام إدارة متكامل للشركات متعددة الفروع",
      metaTitle: "نظام إدارة شركات متعددة الفروع — تجزئة وجملة وتوزيع بصلاحيات لكل دور وفرع",
      description:
        "نظام واحد لمتاجر التجزئة وشركات الجملة والتوزيع بفرع أو عدة فروع ومستودعات: نقطة البيع والمخزون والمشتريات والعملاء والموظفون والإدارة المالية، بصلاحيات لكل دور وفرع، واعتمادات تفصل من يسجّل عمّن يعتمد، والبيع يستمر حين تنقطع الشبكة.",
      lead:
        "الفرع الثاني يضاعف المشكلات لا الأرباح إن كان النظام مبنيًا لكاونتر واحد: كاشير فرع يرى مخزون فرع آخر، وتحويل بضاعة يُسجَّل في طرف ولا يُسجَّل في الآخر، وخصم يُمنح بلا حد، والمالك يجمع الأرقام يدويًا آخر الشهر. فيزانو صُمم لشركة بفروع ومستودعات وأدوار من اليوم الأول، ويبدأ معك بفرع واحد إن كنت في أول الطريق.",
      sections: [
        {
          heading: "كل شخص يرى فرعه ووظيفته",
          body:
            "الصلاحيات في فيزانو بالدور وبالفرع معًا. أدوار الفرع — مدير الفرع والمبيعات والمخزون والمشتريات والموارد البشرية وعلاقات العملاء — ترى فرعها فقط: كاشير الفرع الأول لا يرى مبيعات ولا مخزون الفرع الثاني. مدير الفرع يدير فرعه: المستخدمين والمخزون والمبيعات والمشتريات والعملاء، ويطّلع على موظفيه وحضورهم دون رواتبهم. المالك والمدير العام والمدير المالي والإدارة المالية يرون الشركة كلها.",
          bullets: [
            "اثنا عشر دورًا ثابتًا: مالك الأعمال، مدير عام، مدير مالي، إدارة مالية، مدير فرع، مبيعات، مخزون، مشتريات، موارد بشرية، علاقات عملاء، مدير الموقع، مستعرض",
            "نطاق الفرع يُطبَّق على الشاشات والتقارير والتصدير والمزامنة معًا",
            "سجل نشاط يذكر من غيّر ماذا ومتى",
          ],
        },
        {
          heading: "اعتمادات تفصل من يسجّل عمّن يعتمد",
          body:
            "المالك لا يستطيع أن يقف عند كل كاونتر في كل فرع، فالنظام يطبّق قواعده نيابة عنه. الخصم فوق الحد الذي تحدده الشركة والسعر تحت الحد الأدنى يحتاجان معتمِدًا، وما بيع بسعر مخالف أثناء الانقطاع يُعلَّم للمراجعة. الدفعات والمرتجعات والمصروفات فوق حد الاعتماد تحتاج المالك أو المدير العام أو المدير المالي، وفروقات الجرد يعتمدها مدير الفرع أو الإدارة قبل أن تُطبَّق.",
          bullets: [
            "حد خصم للكاشير (10% افتراضيًا) وحد أدنى للسعر",
            "وردية صندوق تُغلق بجرد فعلي، ومدير يعتمد الفرق",
            "حد ائتمان وإيقاف ائتمان لكل عميل، يضعهما مدير",
            "مسيّرات الرواتب تعتمدها الإدارة المالية قبل أن تُسجَّل في المصروفات",
          ],
        },
        {
          heading: "تجزئة وجملة وتوزيع في نظام واحد",
          body:
            "الفرع الذي يبيع على الكاونتر وفريق المبيعات الذي يخدم عملاء الجملة يعملان على البيانات نفسها. الكاشير يبيع بالباركود والعبوة والوزن، وفريق المبيعات يصدر عروض أسعار تتحول إلى أوامر بيع ثم فواتير، بشروط سداد بالأيام للعملاء الكبار. كل ذلك يخصم من المخزون نفسه ويصب في كشف حساب العميل نفسه.",
          bullets: [
            "عروض الأسعار وأوامر البيع تخضع لحد الخصم والحد الأدنى للسعر نفسيهما",
            "بيع آجل بشروط سداد وحد ائتمان، وكشوف حساب وأعمار ديون",
            "مجموعات عملاء، ومسار للعملاء المحتملين، ومتابعات لفريق المبيعات",
          ],
        },
        {
          heading: "مستودعات متعددة وتحويلات موثّقة",
          body:
            "لكل فرع مستودع أو أكثر، ولكل مستودع رصيده المشتق من دفتر الحركات. التحويل يُسجَّل مرة واحدة بحركتين متقابلتين في اللحظة نفسها: خروج من المستودع المرسِل ودخول إلى المستقبِل، بالكمية والدفعة ومن سجّله. البضاعة لا تُحتسب في مكانين ولا تضيع بينهما. والجرد يتم لكل مستودع على حدة.",
        },
        {
          heading: "المشتريات والموظفون والإدارة المالية",
          body:
            "كل فرع يطلب بضاعته بأوامر شراء ويستلمها في مستودعه، وفواتير الموردين ودفعاتهم تمر بقواعد الاعتماد نفسها. الموارد البشرية تتابع موظفي كل فرع وحضورهم وإجازاتهم وسُلفهم ومسيّرات رواتبهم. والإدارة المالية ترى الشركة كلها: الحسابات البنكية ومطابقة كشوف تطبيقات البنوك، والمصروفات والموازنات، والأرباح والخسائر والتدفق النقدي، وأعمار الذمم.",
        },
        {
          heading: "تقارير للفرع وللشركة",
          body:
            "كل دور يرى تقاريره في حدود نطاقه: مدير الفرع وفريقه يرون أرقام فرعهم، والمالك والمدير العام يرون الشركة كلها مجمّعة: المبيعات والهامش وأداء المنتجات وقيمة المخزون والمشتريات والمرتجعات، لأي فترة. التقارير تُصدَّر CSV.",
        },
        {
          heading: "ابدأ بفرع واحد وكبر بإعداد",
          body:
            "المتجر أو الشركة بفرع واحد يبدأ بأصغر باقة. حين يُفتح الفرع الثاني يضيفه المالك أو المدير العام من الإعدادات، ويعيّن مديره، ويحدد مستودعاته، ويرفع الباقة إن تجاوز سعتها. لا نظام جديد ولا نقل بيانات، وكل جهاز في كل فرع يواصل البيع بلا اتصال ويزامن طابوره مستقلًا.",
        },
      ],
      faq: [
        ["هل يستطيع مدير الفرع إنشاء مستخدمين لفرعه؟", "نعم، مدير الفرع يدير مستخدمي فرعه ويعيّن لهم أدوار الفرع فقط. تعيين المالك وإدارة الاشتراك تبقى للمالك وحده، وإنشاء فرع جديد للمالك أو المدير العام."],
        ["هل يمكن أن يكون للفرع أكثر من مستودع؟", "نعم. لكل فرع مستودعات متعددة، والتحويلات ممكنة بين مستودعات الفرع الواحد أو بين الفروع."],
        ["هل يناسب شركة جملة أو توزيع بلا كاونتر؟", "نعم. البيع يتم بعروض الأسعار وأوامر البيع والفواتير الآجلة بحد ائتمان وشروط سداد، والمخزون بمستودعات متعددة، والتحصيل بكشوف الحساب وأعمار الديون. نقطة البيع تُستخدم حيث يوجد كاونتر."],
        ["كيف يعمل الفرع أثناء انقطاع الإنترنت؟", "كل جهاز يحتفظ ببيانات فرعه ويواصل البيع وتحصيل الدفعات والمرتجعات والاستلام والجرد بلا اتصال، ثم يزامن طابوره مستقلًا عن الفروع الأخرى عند عودة الشبكة."],
        ["هل الإدارة المالية برنامج محاسبة كامل؟", "الإدارة المالية في فيزانو تعطيك أرقام يومك من المستندات نفسها: الحسابات البنكية، والمصروفات والموازنات، والأرباح والخسائر، والتدفق النقدي، وأعمار الذمم، والزكاة. وهي ليست دفتر أستاذ بقيود يومية؛ إن كان لديك محاسب يأخذ التقارير بصيغة CSV."],
        ["هل تُحسب الباقة بعدد الفروع؟", "لكل باقة سعة مستخدمين وفروع ومستودعات، ولا رسوم على كل عملية. الترقية تسري فور سداد فاتورتها النسبية."],
      ],
      cta: "جرّب فيزانو على فروعك وأدوار فريقك",
    },
    en: {
      title: "Integrated management for multi-branch companies",
      metaTitle: "Multi-branch company management — retail, wholesale and distribution with access by role and branch",
      description:
        "One system for retail chains, wholesalers and distributors with one branch or many and several warehouses: point of sale, inventory, purchasing, customers, HR and financial management, with access by role and branch, approvals that separate who records from who approves, and selling that continues when the network drops.",
      lead:
        "A second branch doubles the problems, not the profit, if the system was built for a single counter: a cashier sees another branch's stock, a transfer is recorded at one end and not the other, discounts are given without a limit, and the owner assembles the figures by hand at month end. Vezano was designed for a company with branches, warehouses and roles from day one, and starts with you on one branch if that is where you are.",
      sections: [
        {
          heading: "Everyone sees their branch and their job",
          body:
            "Access in Vezano is set by role and by branch together. Branch roles — branch manager, sales, inventory, purchasing, HR and CRM — see their own branch only: branch one's cashier sees neither the sales nor the stock of branch two. A branch manager runs their branch: users, stock, sales, purchasing and customers, and sees their staff and attendance but not salaries. The owner, general manager, CFO and finance team see the whole company.",
          bullets: [
            "Twelve fixed roles: business owner, general manager, CFO, finance department, branch manager, sales, inventory, purchasing, HR, CRM, website manager, viewer",
            "Branch scope applies to screens, reports, exports and sync alike",
            "An activity log that says who changed what, and when",
          ],
        },
        {
          heading: "Approvals that separate who records from who approves",
          body:
            "The owner cannot stand at every counter in every branch, so the system applies the rules on their behalf. A discount above the company's limit or a price below the floor needs an approver, and anything sold at an out-of-rule price during an outage is flagged for review. Payments, refunds and expenses above the approval threshold need the owner, general manager or CFO, and stock-count variances are approved by the branch manager or head office before they apply.",
          bullets: [
            "A cashier discount limit (10% by default) and a price floor",
            "Cash shifts close with a counted drawer, and a manager signs off the difference",
            "A credit limit and a credit hold per customer, set by a manager",
            "Payroll runs approved by finance before they post to expenses",
          ],
        },
        {
          heading: "Retail, wholesale and distribution in one system",
          body:
            "The branch selling over the counter and the sales team serving wholesale customers work on the same data. The cashier sells by barcode, pack and weight; the sales team issues quotations that become sales orders and then invoices, with payment terms in days for larger customers. All of it draws on the same stock and lands on the same customer statement.",
          bullets: [
            "Quotations and sales orders are held to the same discount limit and price floor",
            "Credit sales with payment terms and a credit limit, statements and ageing",
            "Customer groups, a lead pipeline and follow-ups for the sales team",
          ],
        },
        {
          heading: "Several warehouses, documented transfers",
          body:
            "Each branch has one warehouse or more, and each warehouse has its own balance derived from the movement ledger. A transfer is recorded once as two matching movements at the same moment: out of the sending warehouse and into the receiving one, with the quantity, the batch and who recorded it. Goods are never counted in two places or lost in between. Stock counts are done warehouse by warehouse.",
        },
        {
          heading: "Purchasing, people and financial management",
          body:
            "Each branch orders its goods with purchase orders and receives them into its warehouse, and supplier bills and payments follow the same approval rules. HR tracks each branch's employees, attendance, leave, advances and payroll runs. Financial management sees the whole company: bank accounts and bank-app statement matching, expenses and budgets, profit and loss, cash flow, and receivables and payables ageing.",
        },
        {
          heading: "Reports for the branch and for the company",
          body:
            "Every role sees its reports within its scope: a branch manager and their team see their branch's figures, while the owner and general manager see the whole company consolidated — sales, margin, product performance, stock value, purchasing and returns, for any period. Reports export to CSV.",
        },
        {
          heading: "Start with one branch, grow with a setting",
          body:
            "A store or company with one branch starts on the smallest plan. When the second branch opens, the owner or general manager adds it in settings, appoints its manager, defines its warehouses and upgrades the plan if it goes past its capacity. No new system and no data migration, and every device in every branch keeps selling offline and syncs its own queue.",
        },
      ],
      faq: [
        ["Can a branch manager create users for their branch?", "Yes; a branch manager manages their branch's users and can give them branch roles only. Appointing an owner and managing the subscription stay with the owner alone, and opening a new branch is for the owner or general manager."],
        ["Can a branch have more than one warehouse?", "Yes. Each branch can have several warehouses, and transfers work between a branch's own warehouses or between branches."],
        ["Does it suit a wholesaler or distributor with no counter?", "Yes. Selling runs on quotations, sales orders and credit invoices with a credit limit and payment terms, stock across several warehouses, and collection through statements and ageing. The point of sale is there wherever you do have a counter."],
        ["How does a branch work during an internet outage?", "Each device keeps its branch's data and carries on with sales, customer payments, returns, goods receipts and counts offline, then syncs its queue independently of the other branches when the network returns."],
        ["Is financial management a full accounting package?", "Financial management in Vezano gives you the day's figures from the documents themselves: bank accounts, expenses and budgets, profit and loss, cash flow, receivables and payables ageing, and zakat. It is not a general ledger with journal entries; if you work with an accountant, they take the reports as CSV."],
        ["Is the plan priced per branch?", "Each plan includes a number of users, branches and warehouses, with no per-transaction fees. An upgrade takes effect once its prorated invoice is paid."],
      ],
      cta: "Try Vezano on your branches and your team's roles",
    },
  },
  {
    slug: "offline-pos",
    shot: "pos",
    ar: {
      title: "نقطة بيع تعمل بلا إنترنت",
      metaTitle: "نقطة بيع تعمل بدون إنترنت — كاشير يواصل البيع أثناء الانقطاع",
      description:
        "برنامج كاشير يواصل البيع حين ينقطع الإنترنت أو الكهرباء: المنتجات والأسعار محفوظة على الجهاز، والمبيعات تُحفظ محليًا وتُزامَن مرة واحدة عند عودة الاتصال، دون تكرار ودون فقد.",
      lead:
        "في السودان والخليج ينقطع الإنترنت والكهرباء في أسوأ الأوقات: ساعة الذروة، أو عشية العيد. الكاشير الذي يتوقف مع الشبكة يعطّل الطابور ويخسر البيع. فيزانو مبني على افتراض أن الاتصال سينقطع، لا على أمل ألا ينقطع.",
      sections: [
        {
          heading: "ماذا يحدث لحظة الانقطاع",
          body:
            "لا شيء يتوقف. المنتجات والأسعار والباركود محفوظة على جهاز الكاشير مسبقًا. يظهر شريط «بلا اتصال» أعلى الشاشة ليعرف الكاشير الوضع، ويستمر المسح والبحث والبيع كالمعتاد. كل فاتورة تأخذ مرجعًا محليًا وتُحفظ في طابور على الجهاز نفسه.",
          bullets: [
            "المسح بالباركود والبحث بالاسم يعملان من النسخة المحلية",
            "الخصم على السطر أو الفاتورة، والبيع بالكيلو، وتعليق السلة، كلها متاحة بلا اتصال",
            "الإيصال يُطبع فورًا بالمرجع المحلي",
          ],
        },
        {
          heading: "ماذا يحدث عند عودة الاتصال",
          body:
            "يُرسل الطابور بالترتيب مرة واحدة. الخادم يميّز كل عملية بمعرّفها الفريد، فإذا انقطع الاتصال في منتصف المزامنة وأعاد الجهاز المحاولة، لا تُسجَّل الفاتورة مرتين ولا يُخصم المخزون مرتين. تظهر لك قائمة بالعمليات المحفوظة وأي منها يحتاج انتباهًا.",
          bullets: [
            "مزامنة تلقائية بالترتيب الزمني الصحيح",
            "لا تكرار حتى لو أعيدت المحاولة عشر مرات",
            "شاشة مراجعة لما تمت مزامنته وما تعثّر ولماذا",
          ],
        },
        {
          heading: "ليس الكاشير وحده",
          body:
            "عمليات الفرع اليومية تنضم إلى نفس الطابور: دفعة من عميل، مرتجع أو استرداد، استلام بضاعة، تحويل بين المستودعات، تسوية أو جرد مخزون، دفعة لمورد، وتسجيل الحضور. ما يحتاج اتصالًا: تسجيل الدخول، وفتح وردية الصندوق وإغلاقها، وإضافة منتج أو عميل جديد، والمصروفات، والإعدادات. التقارير واللوحة تعرض آخر نسخة حُمِّلت على الجهاز مع علامة أنها قديمة.",
        },
        {
          heading: "إن كان الإنترنت غير موجود أصلًا",
          body:
            "لبعض الأعمال الإنترنت ليس متقطعًا بل غائبًا. نسخة الخادم الخاص من فيزانو تعمل داخل شبكتك المحلية بلا أي اتصال خارجي: قاعدة البيانات على جهازك، والأجهزة تتصل به عبر الشبكة الداخلية، ورخصة دائمة موقّعة تُتحقق دون إنترنت.",
        },
      ],
      faq: [
        ["كم من الوقت يستطيع الكاشير العمل بلا اتصال؟", "بلا حد زمني. المبيعات تُحفظ على الجهاز حتى تعود الشبكة، سواء بعد دقيقة أو بعد يوم كامل. الحد الوحيد هو مساحة تخزين المتصفح، وهي تكفي لآلاف الفواتير."],
        ["هل يمكن أن تُسجَّل الفاتورة مرتين بعد المزامنة؟", "لا. كل عملية تحمل معرّفًا فريدًا يُولَّد على الجهاز، والخادم يرفض تسجيل المعرّف نفسه مرتين. إعادة المحاولة آمنة دائمًا."],
        ["هل يحتاج الجهاز تطبيقًا خاصًا؟", "لا. فيزانو تطبيق ويب قابل للتثبيت من المتصفح على ويندوز وأندرويد وآيفون وماك. التثبيت يمنحه تخزينًا دائمًا على الجهاز، وهذا ما يجعل الطابور محفوظًا حتى لو أُغلق المتصفح."],
        ["ماذا عن انقطاع الكهرباء؟", "إن كان جهاز الكاشير محمولًا أو على بطارية احتياطية، يواصل العمل كما لو انقطع الإنترنت فقط. الطابور محفوظ على القرص فلا يضيع بإغلاق الجهاز."],
      ],
      cta: "جرّب الكاشير بلا اتصال على منتجاتك",
    },
    en: {
      title: "A point of sale that works offline",
      metaTitle: "Offline POS — a cashier that keeps selling through outages",
      description:
        "Cashier software that keeps selling when the internet or the power goes: products and prices live on the device, sales are saved locally and synced exactly once when the connection returns. No duplicates, nothing lost.",
      lead:
        "Across Sudan and the Gulf, the internet and the power fail at the worst moments: the evening rush, the night before Eid. A till that stops with the network stalls the queue and loses the sale. Vezano is built on the assumption that the connection will drop, not on the hope that it won't.",
      sections: [
        {
          heading: "The moment the connection drops",
          body:
            "Nothing stops. Products, prices and barcodes are already on the cashier's device. An \"offline\" bar appears at the top of the screen so the cashier knows, and scanning, searching and selling carry on as usual. Every receipt gets a local reference and is queued on the device itself.",
          bullets: [
            "Barcode scanning and name search work from the local copy",
            "Line and ticket discounts, sale by weight and held carts all work offline",
            "The receipt prints immediately with its local reference",
          ],
        },
        {
          heading: "When the connection returns",
          body:
            "The queue is sent in order, once. The server recognises every operation by its unique id, so if the connection drops halfway through a sync and the device retries, no receipt is recorded twice and no stock is deducted twice. You get a list of what was saved and anything that needs attention.",
          bullets: [
            "Automatic sync in the correct chronological order",
            "No duplicates, even after ten retries",
            "A review screen for what synced, what failed and why",
          ],
        },
        {
          heading: "Not only the till",
          body:
            "The branch's daily operations join the same queue: a customer payment, a return or refund, a goods receipt, a transfer between warehouses, a stock adjustment or count, a supplier payment, and attendance. What needs a connection: signing in, opening and closing a cash shift, adding a new product or customer, expenses, and settings. Reports and the dashboard show the last copy loaded on the device, marked as out of date.",
        },
        {
          heading: "If there is no internet at all",
          body:
            "For some businesses the internet is not intermittent but absent. The self-hosted edition of Vezano runs inside your local network with no outside connection: the database on your machine, devices reaching it over the LAN, and a signed perpetual licence that verifies without the internet.",
        },
      ],
      faq: [
        ["How long can the cashier work offline?", "There is no time limit. Sales are kept on the device until the network returns, whether that is a minute or a full day. The only limit is the browser's storage, which holds thousands of receipts."],
        ["Can a receipt be recorded twice after syncing?", "No. Every operation carries a unique id generated on the device, and the server refuses to record the same id twice. Retrying is always safe."],
        ["Does the device need a special app?", "No. Vezano is a web app you install from the browser on Windows, Android, iPhone and Mac. Installing grants it durable storage on the device, which is what keeps the queue safe even if the browser is closed."],
        ["What about power cuts?", "If the cashier device is a laptop or on a battery backup, it carries on exactly as it would with the internet down. The queue is on disk, so shutting the device down does not lose it."],
      ],
      cta: "Try the offline cashier with your own products",
    },
  },
  {
    slug: "inventory-expiry",
    shot: "inventory",
    ar: {
      title: "مخزون بالدفعات وتواريخ الصلاحية",
      metaTitle: "برنامج إدارة مخزون بتاريخ الصلاحية — دفعات، FEFO، وتنبيه قبل التلف على اللوحة",
      description:
        "نظام مخزون للأغذية والأدوية ومستحضرات التجميل: كل استلام دفعة بتاريخ صلاحية، والبيع يستهلك الأقرب انتهاءً أولًا، ولوحة تعرض ما يقترب من التلف أو النفاد.",
      lead:
        "التاجر الذي يبيع ما له صلاحية يخسر بطريقتين: بضاعة تنتهي على الرف لأن الأحدث بيعت قبل الأقدم، أو رف يفرغ لأن أحدًا لم يلاحظ أن الرصيد وصل حد الخطر. كلا الخسارتين مسألة معلومات، لا مسألة حظ.",
      sections: [
        {
          heading: "دفتر حركات، لا عمود كمية",
          body:
            "في فيزانو الرصيد ليس رقمًا يُعدَّل يدويًا، بل نتيجة كل حركة مسجّلة: استلام، بيع، تحويل، تسوية، مرتجع، إتلاف. لكل حركة سبب وصاحب ووقت. حين يختلف الرصيد عن الرف، تعرف بالضبط أين حدث الفرق.",
          bullets: [
            "مستودعات متعددة لكل فرع، وتحويلات تُسجَّل خروجًا من مستودع ودخولًا إلى آخر في اللحظة نفسها",
            "لقطة تكلفة مع كل بيع لتقارير FIFO أو المتوسط أو التكلفة القياسية",
            "جرد دوري بفروقات تُعتمد قبل أن تُطبَّق",
          ],
        },
        {
          heading: "الدفعات والصلاحية",
          body:
            "كل استلام بضاعة يمكن أن يحمل رقم دفعة وتاريخ صلاحية. عند البيع يستهلك النظام الدفعة الأقرب انتهاءً أولًا تلقائيًا (FEFO)، فلا يحتاج الكاشير أن يتذكر أي كرتونة تُفتح أولًا. قائمة الصلاحية تعرض الدفعات التي انتهت أو ستنتهي خلال 30 يومًا، بالكمية المتبقية في كل منها.",
          bullets: [
            "استهلاك تلقائي بالأقرب انتهاءً عند البيع",
            "قائمة بما انتهى أو ينتهي خلال 30 يومًا",
            "إتلاف موثّق بسبب وكمية ودفعة",
          ],
        },
        {
          heading: "على اللوحة كل صباح",
          body:
            "حدد لكل منتج حد إعادة الطلب. لوحة المالك ومدير الفرع تعرض ما نزل تحت الحد وما يقترب من انتهاء صلاحيته، محسوبًا من دفتر المخزون لحظة فتحها. لا حاجة لأن يفتح أحد التقرير ليكتشف المشكلة.",
        },
        {
          heading: "البيع بالعبوة والوزن",
          body:
            "الكرتونة والشريط والكيس لها باركود خاص بها وتُخصم من الرصيد بعدد الوحدات الصحيح. البضائع الموزونة تُباع بالكيلو حتى ثلاث منازل عشرية. المخزون يبقى دقيقًا مهما كانت وحدة البيع.",
        },
      ],
      faq: [
        ["أي الأعمال تحتاج الدفعات والصلاحية؟", "كل من يبيع ما ينتهي: الصيدليات وموردو الأدوية، وشركات الأغذية والمشروبات بالجملة والتوزيع، والسوبرماركت وسلاسل التجزئة، ومستحضرات التجميل. كل استلام يحمل دفعته وتاريخها في مستودعه، والبيع يستهلك الأقرب انتهاءً تلقائيًا."],
        ["ماذا لو استُلمت بضاعة بلا تاريخ صلاحية؟", "تاريخ الصلاحية اختياري لكل منتج. المنتجات التي لا تنتهي تُدار بالكمية فقط ولا تظهر في تقارير الصلاحية."],
        ["هل يمكن جرد المخزون دون إيقاف البيع؟", "نعم. الجرد الدوري يُسجَّل كعدّ فعلي مقابل رصيد النظام، والفروقات تُراجع وتُعتمد ثم تُطبَّق كتسوية موثّقة. البيع يستمر أثناء العدّ."],
        ["كيف تُحسب تكلفة البضاعة المباعة؟", "تُحفظ لقطة تكلفة مع كل بيع، ويمكن عرض التقارير بطريقة FIFO أو المتوسط المرجّح أو التكلفة القياسية حسب اختيارك."],
      ],
      cta: "ابدأ بمخزونك الحقيقي، استورده من ملف",
    },
    en: {
      title: "Inventory by batch and expiry date",
      metaTitle: "Inventory software with expiry dates — batches, FEFO and alerts before spoilage",
      description:
        "Stock control for food, pharmacy and cosmetics: every receipt carries a batch and expiry date, sales consume the nearest expiry first, and a dashboard shows what is about to spoil or run out.",
      lead:
        "A merchant who sells perishable goods loses in two ways: stock that expires on the shelf because the newer batch sold before the older one, or a shelf that empties because nobody noticed the balance had reached the danger line. Both losses are information problems, not luck.",
      sections: [
        {
          heading: "A movement ledger, not a quantity column",
          body:
            "In Vezano the balance is not a number someone edits; it is the result of every recorded movement: receipt, sale, transfer, adjustment, return, write-off. Each movement has a reason, an author and a time. When the balance disagrees with the shelf, you know exactly where the difference happened.",
          bullets: [
            "Multiple warehouses per branch, and transfers recorded out of one warehouse and into another at the same moment",
            "A cost snapshot with every sale for FIFO, weighted-average or standard-cost reports",
            "Periodic stock counts whose variances are approved before they apply",
          ],
        },
        {
          heading: "Batches and expiry",
          body:
            "Every goods receipt can carry a batch number and an expiry date. At the till the system consumes the batch closest to expiry first, automatically (FEFO), so the cashier never has to remember which carton to open. The expiry list shows the batches that have expired or will expire within 30 days, with the quantity left in each.",
          bullets: [
            "Automatic nearest-expiry-first consumption at sale",
            "A list of what has expired or expires within 30 days",
            "Documented write-offs with reason, quantity and batch",
          ],
        },
        {
          heading: "On the dashboard every morning",
          body:
            "Set a reorder level per product. The owner's and branch manager's dashboards list what has fallen below that level and what is close to expiry, computed from the stock ledger when they open it. Nobody has to open a report to discover the problem.",
        },
        {
          heading: "Selling by the pack and by weight",
          body:
            "Cartons, strips and sacks have their own barcodes and deduct the right number of units from stock. Weighed goods sell by the kilogram to three decimal places. Stock stays accurate whatever the selling unit.",
        },
      ],
      faq: [
        ["Which businesses need batches and expiry?", "Anyone selling goods that expire: pharmacies and medical suppliers, food and beverage wholesalers and distributors, supermarkets and retail chains, and cosmetics. Every receipt carries its batch and date in its warehouse, and sales consume the earliest expiry automatically."],
        ["What if goods arrive without an expiry date?", "Expiry is optional per product. Products that do not expire are managed by quantity alone and never appear in expiry reports."],
        ["Can we count stock without stopping sales?", "Yes. A periodic count is recorded as a physical count against the system balance; variances are reviewed and approved, then applied as a documented adjustment. Selling continues during the count."],
        ["How is cost of goods sold calculated?", "A cost snapshot is stored with every sale, and reports can be shown by FIFO, weighted average or standard cost, whichever you choose."],
      ],
      cta: "Start with your real stock, imported from a file",
    },
  },
  {
    slug: "customer-debts",
    shot: "debts",
    ar: {
      title: "دفتر ديون العملاء",
      metaTitle: "دفتر ديون العملاء — كشف حساب برصيد متحرك، أعمار الديون، وسداد موثّق",
      description:
        "دفتر ديون رقمي يشتق رصيد كل عميل من فواتيره ودفعاته وإشعاراته الدائنة، لا من رقم يُكتب باليد: كشف حساب لأي فترة برصيد افتتاحي وختامي، أعمار الديون بعد تاريخ الاستحقاق، سداد نقدي أو بتحويل بنكي موثّق، وتنبيه على اللوحة بمن تأخر.",
      lead:
        "البيع الآجل جزء من التجارة في أسواقنا، والمشكلة ليست في أن تبيع بالدين بل في ألا تعرف من يدين لك بكم ومنذ متى، وألا تملك ورقة تحسم الخلاف حين يقول العميل «دفعتها». دفتر الديون في فيزانو يجيب عن الأسئلة الثلاثة من المستندات نفسها.",
      sections: [
        {
          heading: "كيف يولد الدين",
          body:
            "الدين يبدأ فاتورة آجلة على عميل مسجّل، لا على «زبون» مجهول. عند البيع تختار العميل وتحدد شروط السداد بالأيام، فيحسب النظام تاريخ الاستحقاق تلقائيًا. هذا التاريخ هو ما يُقاس عليه التأخر لاحقًا، لا تاريخ الفاتورة.",
          bullets: [
            "بيع آجل من نقطة البيع مباشرة، والفاتورة تُقيَّد على حساب العميل فورًا",
            "شروط سداد بالأيام لكل فاتورة، وتاريخ استحقاق يُشتق منها",
            "لا بيع آجل بلا عميل محدد، فلا يضيع دين في فاتورة مجهولة",
          ],
        },
        {
          heading: "ما تراه في شاشة الديون",
          body:
            "ثلاثة أرقام أعلى الشاشة تلخص الوضع: إجمالي المستحق على العملاء، الجزء المتأخر منه عن موعده، والأرصدة الدائنة التي لهم عندك. تحتها قائمة المدينين بالبحث بالاسم أو الهاتف، ورصيد كل عميل أمامه. اختيار عميل يفتح كشف حسابه في الصفحة نفسها.",
        },
        {
          heading: "كشف الحساب: كل حركة بمستندها",
          body:
            "الكشف لأي فترة تختارها، يبدأ برصيد افتتاحي هو نتيجة كل ما سبق الفترة، ثم يعرض كل حركة بتاريخها ومرجعها: الفاتورة في خانة المدين، والدفعة أو الإشعار الدائن في خانة الدائن، ورصيد متحرك بعد كل سطر، وينتهي برصيد ختامي. لا يوجد حقل رصيد يُعدَّل باليد في أي مكان؛ الرصيد دائمًا حاصل جمع المستندات، فإن اختلف العميل معك تعودان إلى الفاتورة أو الدفعة بعينها.",
          bullets: [
            "رصيد افتتاحي وختامي للفترة، ورصيد متحرك بعد كل حركة",
            "ثلاثة أنواع حركات فقط: فاتورة، دفعة، إشعار دائن، ولكل منها رقم مرجعي",
            "ما تراه على الشاشة هو ما يُطبع، من المصدر نفسه",
          ],
        },
        {
          heading: "تسجيل السداد",
          body:
            "الدفعة تُسجَّل على الفاتورة نقدًا أو تحويلًا بنكيًا. التحويل (من تطبيق بنكك أو غيره) يُسجَّل يدويًا باسم بنك المرسل ورقم العملية والحساب البنكي للشركة الذي استقبله، فتُطابقه لاحقًا مع كشف التطبيق أو البنك. لا يوجد ربط مباشر مع البنك. الدفعة الجزئية تُخصم ويبقى الباقي مستحقًا بتاريخ استحقاقه الأصلي. كل دفعة تحمل من سجّلها ومتى.",
          bullets: [
            "نقد أو تحويل بنكي بمرجع وحساب مستلم",
            "دفعات جزئية بلا حد لعددها",
            "الدفعة التي تتجاوز حد الاعتماد الذي تحدده الشركة تحتاج تحقق مالك أو مدير عام أو مدير مالي",
          ],
        },
        {
          heading: "التخفيض الموثّق، لا الحذف",
          body:
            "المرتجع يصدر إشعارًا دائنًا مرقّمًا يُخصم من حساب العميل مرة واحدة. الحركة المالية المسجّلة لا تُعدَّل ولا تُحذف؛ الخطأ يُصحَّح بحركة مقابلة مرتبطة بالأصل. لهذا يبقى الكشف صالحًا كدليل: كل سطر فيه له مستند، وكل مستند له صاحب في سجل التدقيق.",
        },
        {
          heading: "من تأخر ومنذ متى",
          body:
            "تقرير أعمار الديون يصنّف كل مستحق بعدد الأيام بعد تاريخ استحقاقه: من 1 إلى 30 يومًا، من 31 إلى 60، من 61 إلى 90، وأكثر من 90. والفاتورة التي تجاوزت موعدها للتو تظهر في تنبيهات لوحة المالك في اليوم نفسه، فتعرف من تتصل به هذا الأسبوع دون أن تفتح تقريرًا.",
        },
        {
          heading: "الفروع والصلاحيات",
          body:
            "مستخدم الفرع يرى ديون فرعه فقط، والمالك والمدير العام يريان الشركة كلها. حتى عرض كشف الحساب يُسجَّل في سجل التدقيق بمن عرضه ومتى. الموردون لهم الدفتر نفسه في الاتجاه المعاكس: ما تدين به لكل مورد وأعمار ذلك الدين.",
        },
      ],
      faq: [
        ["هل يمكن للكاشير أن يبيع بالدين لأي عميل؟", "البيع الآجل يتطلب اختيار عميل مسجّل بالاسم والهاتف، ويمكن حصر الصلاحية بحسب الدور. الفاتورة تُقيَّد على حسابه فورًا وتظهر في كشفه بتاريخ استحقاقها."],
        ["كيف أُري العميل كشف حسابه؟", "افتح كشفه لأي فترة من شاشة الديون واطبعه من المتصفح، أو اعرضه على الشاشة أمامه. كل سطر فيه يحمل رقم الفاتورة أو الدفعة، فالخلاف يُحسم بالمستند لا بالذاكرة."],
        ["ماذا لو دفع العميل جزءًا من المبلغ؟", "تُسجَّل دفعة جزئية على الفاتورة ويبقى الباقي مستحقًا بتاريخ الاستحقاق الأصلي، فيظهر في أعمار الديون بعمره الحقيقي لا من تاريخ آخر دفعة."],
        ["هل يمكن إلغاء فاتورة آجلة بعد تسجيلها؟", "لا شيء يُلغى في صمت. المرتجع أو التصحيح يصدر إشعار دائن مرقّمًا يُخصم من حساب العميل، ويبقى الأثر كاملًا في الكشف وسجل التدقيق."],
        ["هل للموردين دفتر مماثل؟", "نعم. لكل مورد رصيد وأعمار مستحقات، ودفعات الموردين تخضع لقواعد الاعتماد نفسها التي تخضع لها دفعات العملاء الكبيرة."],
      ],
      cta: "انقل دفتر ديونك إلى فيزانو",
    },
    en: {
      title: "Customer debt ledger",
      metaTitle: "Customer debt ledger — running-balance statements, ageing and documented payments",
      description:
        "A digital debt ledger that derives every customer's balance from their invoices, payments and credit notes, not from a hand-written number: a statement for any period with opening and closing balances, ageing past the due date, cash or documented bank-transfer payments, and a dashboard alert for who is late.",
      lead:
        "Selling on credit is part of trade in our markets. The problem is not selling on credit; it is not knowing who owes you how much and since when, and having no document to settle it when the customer says \"I paid that\". The debt ledger in Vezano answers all three from the documents themselves.",
      sections: [
        {
          heading: "How a debt is born",
          body:
            "A debt starts as a credit invoice on a registered customer, never on an anonymous walk-in. At the sale you pick the customer and set payment terms in days, and the system derives the due date. That due date, not the invoice date, is what lateness is measured against later.",
          bullets: [
            "Credit sales straight from the point of sale, posted to the customer's account at once",
            "Payment terms in days per invoice, with the due date derived from them",
            "No credit sale without a named customer, so no debt is lost in an anonymous receipt",
          ],
        },
        {
          heading: "What the debts screen shows",
          body:
            "Three figures at the top summarise the position: the total owed by customers, the part of it that is past due, and the credit balances customers hold with you. Below them, the list of debtors, searchable by name or phone, each with their balance. Choosing a customer opens their statement on the same page.",
        },
        {
          heading: "The statement: every movement with its document",
          body:
            "The statement covers any period you choose. It opens with an opening balance, the result of everything before the period, then lists each movement with its date and reference: the invoice in the debit column, the payment or credit note in the credit column, a running balance after every line, and a closing balance at the end. There is no editable balance field anywhere; the balance is always the sum of the documents, so a dispute goes back to the specific invoice or payment.",
          bullets: [
            "Opening and closing balances for the period, and a running balance after each movement",
            "Only three kinds of movement: invoice, payment, credit note, each with a reference number",
            "What you see on screen is what prints, from the same source",
          ],
        },
        {
          heading: "Recording a payment",
          body:
            "A payment is recorded against the invoice in cash or by bank transfer. A transfer (from Bankak or another bank app) is recorded by hand with the sender's bank, the transaction number and the company bank account that received it, so you can match it to the app's or the bank's statement later. There is no direct link to the bank. A partial payment is deducted and the remainder stays due under its original due date. Every payment carries who recorded it and when.",
          bullets: [
            "Cash or bank transfer with a reference and a receiving account",
            "Partial payments, as many as needed",
            "A payment above the approval threshold the company sets needs verification by the owner, general manager or CFO",
          ],
        },
        {
          heading: "Documented reduction, never deletion",
          body:
            "A return issues a numbered credit note that reduces the customer's account exactly once. A recorded financial movement is never edited or deleted; a mistake is corrected by a counter-movement linked to the original. That is why the statement remains valid as evidence: every line has a document, and every document has an author in the audit log.",
        },
        {
          heading: "Who is late, and since when",
          body:
            "The ageing report sorts every outstanding amount by days past its due date: 1 to 30, 31 to 60, 61 to 90, and over 90. An invoice that has just passed its due date appears in the owner's dashboard alerts the same day, so you know who to call this week without opening a report.",
        },
        {
          heading: "Branches and permissions",
          body:
            "A branch user sees only their branch's debts; the owner and general manager see the whole company. Even viewing a statement is written to the audit log with who viewed it and when. Suppliers get the same ledger in reverse: what you owe each supplier and how old that debt is.",
        },
      ],
      faq: [
        ["Can the cashier sell on credit to anyone?", "A credit sale requires choosing a registered customer with a name and phone, and the permission can be limited by role. The invoice is posted to their account at once and appears on their statement with its due date."],
        ["How do I show a customer their statement?", "Open their statement for any period from the debts screen and print it from the browser, or show it on screen in front of them. Every line carries the invoice or payment number, so a dispute is settled by the document, not by memory."],
        ["What if a customer pays part of the amount?", "A partial payment is recorded against the invoice and the remainder stays due under the original due date, so it appears in ageing at its true age, not from the date of the last payment."],
        ["Can a credit invoice be cancelled after it is recorded?", "Nothing is cancelled silently. A return or correction issues a numbered credit note that reduces the customer's account, and the full trail stays in the statement and the audit log."],
        ["Is there the same ledger for suppliers?", "Yes. Every supplier has a balance and an ageing of what is owed, and supplier payments follow the same approval rules as large customer payments."],
      ],
      cta: "Move your debt ledger into Vezano",
    },
  },
  {
    slug: "store-page",
    shot: "store-page",
    ar: {
      title: "صفحة عامة لشركتك أو متجرك على الإنترنت",
      metaTitle: "صفحة عامة لشركتك — واجهة إلكترونية بغلاف ومنتجات وقنوات تواصل وخريطة، جاهزة لـ Google",
      description:
        "كل اشتراك في فيزانو يشمل صفحة عامة لنشاطك: غلاف وشعار، منتجات بالصور والأسعار، زر واتساب، ساعات العمل والموقع على الخريطة، جاهزة لتفهرسها محركات البحث مثل Google، دون مصمم ولا استضافة.",
      lead:
        "العميل اليوم يبحث عن الشركة في Google قبل أن يتصل بها، ويريد قناة تواصل مباشرة لا صفحة على شبكة اجتماعية. صفحة شركتك على فيزانو تُنشأ من بياناتك الموجودة أصلًا في النظام، وتصبح على الإنترنت بضغطة، وعنوانها vezano.app/s/اسم-الشركة.",
      sections: [
        {
          heading: "ما الذي تحصل عليه",
          body:
            "صفحة هبوط كاملة لا مجرد بطاقة تعريف: غلاف بصورة المحل، شعار، شارة نوع النشاط والمدينة، أزرار واتساب واتصال، شبكة منتجات بالصور والأسعار من مخزونك، نبذة، معرض صور، ساعات العمل، والعنوان مع رابط الخريطة.",
          bullets: [
            "تعمل على الهاتف بزر واتساب ثابت أسفل الشاشة",
            "بالعربية من اليمين لليسار أو بالإنجليزية حسب محتواك، ووضع داكن تلقائي",
            "بلون نشاطك، دون قوالب معقدة تحتاج مصممًا",
          ],
        },
        {
          heading: "تظهر في Google والخرائط",
          body:
            "الصفحة تُبنى من الخادم كـ HTML حقيقي، بعنوان ووصف وبيانات منظمة من نوع LocalBusiness: الاسم والهاتف والعنوان وساعات العمل والصور والمنتجات بأسعارها. هذه هي البيانات التي تجعل محلك يظهر حين يبحث أحدهم عن نشاطك في مدينتك.",
          bullets: [
            "خريطة موقع خاصة بالمتاجر (sitemap) تقرؤها محركات البحث، وتُضاف إليها صفحتك عند النشر",
            "دليل المتاجر على فيزانو يربط صفحتك من صفحة مفهرسة",
            "بطاقة معاينة عند مشاركة الرابط في واتساب وفيسبوك",
          ],
        },
        {
          heading: "من داخل النظام، بلا عمل مزدوج",
          body:
            "المنتجات المميزة تُختار من مخزونك بأسعارها الحالية، فلا تكتب السعر مرتين. الصور تُرفع من الهاتف وتُصغَّر تلقائيًا. المعاينة تُريك الصفحة كما سيراها الزائر قبل النشر، وقائمة الاكتمال تخبرك بما ينقص.",
        },
        {
          heading: "أنت تتحكم في الظهور",
          body:
            "الصفحة عامة حين تنشرها وتختفي حين توقفها. يمكنك إبقاءها متاحة برابطها فقط دون أن تظهر في دليل فيزانو أو خريطة الموقع، وحذف أي صورة أو منتج منها في أي وقت.",
        },
      ],
      faq: [
        ["هل تحتاج الصفحة إلى اشتراك إضافي أو استضافة؟", "لا. الصفحة جزء من كل باقة وتُستضاف على vezano.app مع شهادة HTTPS. لا رسوم إضافية."],
        ["هل يمكن ربط نطاقي الخاص بها؟", "ليس بعد. العنوان الحالي vezano.app/s/اسم-متجرك. ربط النطاق الخاص على قائمة التطوير."],
        ["هل يرى الزائر أسعاري ومخزوني كله؟", "لا. لا يظهر إلا ما تختاره صراحةً كمنتج مميز، وبالسعر الذي تحدده في النظام. المخزون والتكاليف لا تُنشر أبدًا."],
        ["كيف يتواصل الزبون معي من الصفحة؟", "زر واتساب مباشر برقمك، وزر اتصال، والبريد، ورابط الاتجاهات على الخريطة. لا نماذج تحتاج متابعة."],
      ],
      cta: "أنشئ صفحة شركتك في ظهيرة واحدة",
    },
    en: {
      title: "A public web page for your company or store",
      metaTitle: "A public page for your company — an online presence with cover, products, contact channels and a map, ready for Google",
      description:
        "Every Vezano subscription includes a public page for the business: cover and logo, products with photos and prices, a WhatsApp button, opening hours and a map link, ready for search engines such as Google to index, with no designer and no hosting.",
      lead:
        "Customers look a shop up on Google before they visit, and they want a WhatsApp number, not a Facebook page. Your store page on Vezano is built from the data already in the system, goes live with one click, and lives at vezano.app/s/your-store.",
      sections: [
        {
          heading: "What you get",
          body:
            "A full landing page, not a business card: a cover photo, a logo, a badge with your trade and city, WhatsApp and call buttons, a grid of products with photos and prices from your inventory, an about section, a photo gallery, opening hours, and your address with a map link.",
          bullets: [
            "Works on phones with a sticky WhatsApp button",
            "Arabic right-to-left or English, following your content, with automatic dark mode",
            "In your brand colour, without templates that need a designer",
          ],
        },
        {
          heading: "Found on Google and on maps",
          body:
            "The page is served as real HTML with a title, a description and LocalBusiness structured data: name, phone, address, opening hours, photos and products with prices. That is the data that makes a shop appear when someone searches for your trade in your city.",
          bullets: [
            "A stores sitemap that search engines read; your page joins it when you publish",
            "The Vezano store directory links to your page from an indexed page",
            "A preview card when the link is shared on WhatsApp or Facebook",
          ],
        },
        {
          heading: "From inside the system, no double work",
          body:
            "Featured products are picked from your inventory at their current prices, so you never type a price twice. Photos are uploaded from a phone and resized automatically. The preview shows the page exactly as a visitor will see it before you publish, and the completeness checklist tells you what is missing.",
        },
        {
          heading: "You control the exposure",
          body:
            "The page is public when you publish it and gone when you unpublish. You can keep it reachable by link only, without listing it in the Vezano directory or the sitemap, and remove any photo or product at any time.",
        },
      ],
      faq: [
        ["Does the page need an extra subscription or hosting?", "No. It is part of every plan and hosted on vezano.app with HTTPS. No extra fees."],
        ["Can I connect my own domain?", "Not yet. The address is vezano.app/s/your-store. Custom domains are on the roadmap."],
        ["Do visitors see all my prices and stock?", "No. Only what you explicitly feature is shown, at the price you set in the system. Stock levels and costs are never published."],
        ["How do customers reach me from the page?", "A direct WhatsApp button with your number, a call button, email, and a directions link on the map. No forms to follow up."],
      ],
      cta: "Build your company page in one afternoon",
    },
  },
];

export function solution(slug) {
  return SOLUTIONS.find((item) => item.slug === slug) || null;
}
