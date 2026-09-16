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
            "كل عملية على مستوى الفرع تنضم إلى نفس الطابور: استلام بضاعة، تحويل بين المستودعات، تسوية مخزون، تسجيل دفعة من عميل. الفرع يواصل عمله اليومي كاملًا ثم يُزامن دفعة واحدة.",
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
            "Every branch-level operation joins the same queue: goods receipt, transfers between warehouses, stock adjustments, a customer payment. The branch carries on with its full day's work and syncs in one go.",
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
      metaTitle: "برنامج إدارة مخزون بتاريخ الصلاحية — دفعات، FEFO، وتنبيهات قبل التلف",
      description:
        "نظام مخزون للأغذية والأدوية ومستحضرات التجميل: كل استلام دفعة بتاريخ صلاحية، والبيع يستهلك الأقرب انتهاءً أولًا، وتنبيه كل صباح بما يقترب من التلف أو النفاد.",
      lead:
        "التاجر الذي يبيع ما له صلاحية يخسر بطريقتين: بضاعة تنتهي على الرف لأن الأحدث بيعت قبل الأقدم، أو رف يفرغ لأن أحدًا لم يلاحظ أن الرصيد وصل حد الخطر. كلا الخسارتين مسألة معلومات، لا مسألة حظ.",
      sections: [
        {
          heading: "دفتر حركات، لا عمود كمية",
          body:
            "في فيزانو الرصيد ليس رقمًا يُعدَّل يدويًا، بل نتيجة كل حركة مسجّلة: استلام، بيع، تحويل، تسوية، مرتجع، إتلاف. لكل حركة سبب وصاحب ووقت. حين يختلف الرصيد عن الرف، تعرف بالضبط أين حدث الفرق.",
          bullets: [
            "مستودعات متعددة لكل فرع، وتحويلات بحالة «في الطريق» حتى تُستلم",
            "لقطة تكلفة مع كل بيع لتقارير FIFO أو المتوسط أو التكلفة القياسية",
            "جرد دوري بفروقات تُعتمد قبل أن تُطبَّق",
          ],
        },
        {
          heading: "الدفعات والصلاحية",
          body:
            "كل استلام بضاعة يمكن أن يحمل رقم دفعة وتاريخ صلاحية. عند البيع يستهلك النظام الدفعة الأقرب انتهاءً أولًا تلقائيًا (FEFO)، فلا يحتاج الكاشير أن يتذكر أي كرتونة تُفتح أولًا. تقرير الصلاحية يعرض ما سينتهي خلال الأيام القادمة بالكمية والقيمة.",
          bullets: [
            "استهلاك تلقائي بالأقرب انتهاءً عند البيع",
            "تقرير بما ينتهي خلال 7 أو 30 أو 90 يومًا",
            "إتلاف موثّق بسبب وكمية ودفعة",
          ],
        },
        {
          heading: "تنبيهات كل صباح",
          body:
            "حدد لكل منتج حد إعادة الطلب. فحص يومي مجدول يراجع كل الفروع ويضع على لوحة المالك ومدير الفرع ما نقص وما يقترب من انتهاء صلاحيته. لا حاجة لأن يفتح أحد التقرير ليكتشف المشكلة.",
        },
        {
          heading: "البيع بالعبوة والوزن",
          body:
            "الكرتونة والشريط والكيس لها باركود خاص بها وتُخصم من الرصيد بعدد الوحدات الصحيح. البضائع الموزونة تُباع بالكيلو حتى ثلاث منازل عشرية. المخزون يبقى دقيقًا مهما كانت وحدة البيع.",
        },
      ],
      faq: [
        ["هل يناسب الصيدليات ومحلات الأغذية؟", "نعم، هذان هما النشاطان اللذان صُممت الدفعات والصلاحية من أجلهما. كل استلام يحمل دفعته وتاريخها، والبيع يستهلك الأقدم انتهاءً تلقائيًا."],
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
        "Stock control for food, pharmacy and cosmetics: every receipt carries a batch and expiry date, sales consume the nearest expiry first, and every morning you are told what is about to spoil or run out.",
      lead:
        "A merchant who sells perishable goods loses in two ways: stock that expires on the shelf because the newer batch sold before the older one, or a shelf that empties because nobody noticed the balance had reached the danger line. Both losses are information problems, not luck.",
      sections: [
        {
          heading: "A movement ledger, not a quantity column",
          body:
            "In Vezano the balance is not a number someone edits; it is the result of every recorded movement: receipt, sale, transfer, adjustment, return, write-off. Each movement has a reason, an author and a time. When the balance disagrees with the shelf, you know exactly where the difference happened.",
          bullets: [
            "Multiple warehouses per branch, transfers held \"in transit\" until received",
            "A cost snapshot with every sale for FIFO, weighted-average or standard-cost reports",
            "Periodic stock counts whose variances are approved before they apply",
          ],
        },
        {
          heading: "Batches and expiry",
          body:
            "Every goods receipt can carry a batch number and an expiry date. At the till the system consumes the batch closest to expiry first, automatically (FEFO), so the cashier never has to remember which carton to open. The expiry report shows what expires in the coming days, by quantity and value.",
          bullets: [
            "Automatic nearest-expiry-first consumption at sale",
            "A report of what expires within 7, 30 or 90 days",
            "Documented write-offs with reason, quantity and batch",
          ],
        },
        {
          heading: "Alerts every morning",
          body:
            "Set a reorder level per product. A scheduled daily scan reviews every branch and puts what is short, and what is close to expiry, on the owner's and branch manager's dashboards. Nobody has to open a report to discover the problem.",
        },
        {
          heading: "Selling by the pack and by weight",
          body:
            "Cartons, strips and sacks have their own barcodes and deduct the right number of units from stock. Weighed goods sell by the kilogram to three decimal places. Stock stays accurate whatever the selling unit.",
        },
      ],
      faq: [
        ["Is it suited to pharmacies and grocery stores?", "Yes; those are the two trades batches and expiry were designed for. Every receipt carries its batch and date, and sales consume the earliest expiry automatically."],
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
            "الدفعة تُسجَّل على الفاتورة نقدًا أو تحويلًا بنكيًا. التحويل يحمل اسم بنك المرسل وآخر أربعة أرقام من مرجعه والحساب البنكي للشركة الذي استقبله، فتُطابقه مع كشف البنك لاحقًا. الدفعة الجزئية تُخصم ويبقى الباقي مستحقًا بتاريخ استحقاقه الأصلي. كل دفعة تحمل من سجّلها ومتى.",
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
            "A payment is recorded against the invoice in cash or by bank transfer. A transfer carries the sender's bank, the last four digits of its reference and the company bank account that received it, so you can match it to the bank statement later. A partial payment is deducted and the remainder stays due under its original due date. Every payment carries who recorded it and when.",
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
    slug: "multi-branch",
    shot: "dashboard",
    ar: {
      title: "إدارة فروع ومستودعات متعددة",
      metaTitle: "نظام إدارة فروع متعددة — كل فرع يرى فرعه، والمالك يرى الكل",
      description:
        "نظام مبيعات ومخزون لأعمال متعددة الفروع: صلاحيات على مستوى الفرع، تحويلات بين المستودعات، تقارير لكل فرع أو للشركة كلها، ولوحة واحدة للمالك.",
      lead:
        "الفرع الثاني يضاعف المشكلات لا الأرباح إن كان النظام مبنيًا لمحل واحد. كاشير فرع يرى مخزون فرع آخر، وتحويل بضاعة يُسجَّل في طرف ولا يُسجَّل في الآخر، والمالك يجمع التقارير يدويًا آخر الشهر. فيزانو صُمم للفروع من اليوم الأول.",
      sections: [
        {
          heading: "كل شخص يرى فرعه بالضبط",
          body:
            "الصلاحيات في فيزانو على مستوى الفرع، لا على مستوى الشركة فقط. كاشير الفرع الأول لا يرى مبيعات ولا مخزون الفرع الثاني. مدير الفرع يدير فرعه كاملًا: المستخدمين والمخزون والمبيعات والحضور. المالك والمدير العام يريان الشركة كلها.",
          bullets: [
            "أدوار ثابتة: مالك، مدير عام، مدير فرع، مخزون، مبيعات، مشتريات، موارد بشرية، عملاء، مالية، مشاهد",
            "نطاق الفرع يُطبَّق على الشاشات والتقارير والتصدير والمزامنة معًا",
            "سجل تدقيق يذكر من غيّر ماذا ومن أي فرع",
          ],
        },
        {
          heading: "التحويل بين المستودعات",
          body:
            "التحويل يُسجَّل مرة واحدة ويحمل حالة «في الطريق» حتى يستلمه الفرع الآخر. البضاعة لا تختفي من هنا لتظهر هناك سحريًا، ولا تُحتسب في مكانين. الفرق بين المُرسل والمُستلم يظهر فورًا.",
        },
        {
          heading: "تقارير بأي زاوية",
          body:
            "المبيعات والهامش وأداء المنتجات والمصروفات لأي فترة، لفرع واحد أو للشركة كلها. المالك يقارن الفروع من شاشة واحدة، ومدير الفرع يرى فرعه فقط. كل قائمة تُصدَّر CSV.",
        },
        {
          heading: "ابدأ بفرع واحد وكبر بإعداد",
          body:
            "المحل الواحد يبدأ بأصغر باقة. حين يُفتح الفرع الثاني تضيفه من الإعدادات، وتعيّن مديره، وتحدد مستودعاته. لا تغيير في المنتج ولا نقل بيانات. كل فرع يعمل بلا اتصال مستقلًا ويزامن لوحده.",
        },
      ],
      faq: [
        ["هل يستطيع مدير الفرع إنشاء مستخدمين لفرعه؟", "نعم، مدير الفرع يدير مستخدمي فرعه ضمن نطاقه. تعيين المالك وإدارة الاشتراك تبقى للمالك وحده."],
        ["هل يمكن أن يكون للفرع أكثر من مستودع؟", "نعم. لكل فرع مستودعات متعددة، والتحويلات ممكنة بين مستودعات الفرع الواحد أو بين الفروع."],
        ["كيف يعمل الفرع أثناء انقطاع الإنترنت؟", "كل فرع يحتفظ ببياناته على أجهزته ويواصل البيع والاستلام بلا اتصال، ثم يزامن طابوره مستقلًا عن الفروع الأخرى عند عودة الشبكة."],
        ["هل تُحسب الباقة بعدد الفروع؟", "لكل باقة سعة مستخدمين وفروع ومستودعات. ترقية الباقة فورية، ولا رسوم على كل عملية."],
      ],
      cta: "أضف فرعك الثاني بإعداد، لا بنظام جديد",
    },
    en: {
      title: "Multiple branches and warehouses",
      metaTitle: "Multi-branch management system — each branch sees its own, the owner sees everything",
      description:
        "Sales and inventory for multi-branch businesses: branch-level permissions, transfers between warehouses, reports per branch or company-wide, and one dashboard for the owner.",
      lead:
        "A second branch doubles the problems, not the profit, if the system was built for one shop. A cashier sees another branch's stock, a transfer is recorded at one end and not the other, and the owner assembles reports by hand at month end. Vezano was designed for branches from day one.",
      sections: [
        {
          heading: "Everyone sees exactly their branch",
          body:
            "Permissions in Vezano are branch-scoped, not only company-scoped. Branch one's cashier sees neither the sales nor the stock of branch two. A branch manager runs their branch in full: users, stock, sales, attendance. The owner and general manager see the whole company.",
          bullets: [
            "Fixed roles: owner, general manager, branch manager, inventory, sales, purchasing, HR, CRM, finance, viewer",
            "Branch scope applies to screens, reports, exports and sync alike",
            "An audit log that says who changed what, from which branch",
          ],
        },
        {
          heading: "Transfers between warehouses",
          body:
            "A transfer is recorded once and stays \"in transit\" until the other branch receives it. Goods do not vanish here and magically appear there, and they are never counted in two places. Any difference between sent and received shows up immediately.",
        },
        {
          heading: "Reports from any angle",
          body:
            "Sales, margin, product performance and expenses for any period, for one branch or the whole company. The owner compares branches from one screen; a branch manager sees only theirs. Every list exports to CSV.",
        },
        {
          heading: "Start with one branch, grow with a setting",
          body:
            "A single shop starts on the smallest plan. When the second branch opens you add it in settings, appoint its manager and define its warehouses. No product change, no data migration. Each branch works offline independently and syncs on its own.",
        },
      ],
      faq: [
        ["Can a branch manager create users for their branch?", "Yes; a branch manager manages their branch's users within their scope. Appointing an owner and managing the subscription stay with the owner alone."],
        ["Can a branch have more than one warehouse?", "Yes. Each branch can have several warehouses, and transfers work between a branch's own warehouses or between branches."],
        ["How does a branch work during an internet outage?", "Each branch keeps its data on its own devices and keeps selling and receiving offline, then syncs its queue independently of the other branches when the network returns."],
        ["Is the plan priced per branch?", "Each plan includes a number of users, branches and warehouses. Upgrading is immediate, and there are no per-transaction fees."],
      ],
      cta: "Add your second branch with a setting, not a new system",
    },
  },
  {
    slug: "store-page",
    shot: "store-page",
    ar: {
      title: "صفحة مجانية لمتجرك على الإنترنت",
      metaTitle: "صفحة مجانية لمتجرك — موقع للمحل بغلاف ومنتجات وواتساب وخريطة، يُفهرس في Google",
      description:
        "كل اشتراك في فيزانو يشمل صفحة عامة لنشاطك: غلاف وشعار، منتجات بالصور والأسعار، زر واتساب، ساعات العمل والموقع على الخريطة، تُفهرس في Google تلقائيًا دون مصمم ولا استضافة.",
      lead:
        "الزبون اليوم يبحث عن المحل في Google قبل أن يزوره، ويريد رقم واتساب لا صفحة فيسبوك. صفحة متجرك على فيزانو تُنشأ من بياناتك الموجودة أصلًا في النظام، وتصبح على الإنترنت بضغطة، وعنوانها vezano.app/s/اسم-متجرك.",
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
            "خريطة موقع خاصة بالمتاجر تُقدَّم لـ Google تلقائيًا عند النشر",
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
      cta: "أنشئ صفحة متجرك في ظهيرة واحدة",
    },
    en: {
      title: "A free web page for your store",
      metaTitle: "A free page for your store — a shop site with cover, products, WhatsApp and a map, indexed by Google",
      description:
        "Every Vezano subscription includes a public page for the business: cover and logo, products with photos and prices, a WhatsApp button, opening hours and a map link, indexed by Google automatically, with no designer and no hosting.",
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
            "A stores sitemap is submitted to Google automatically on publish",
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
      cta: "Build your store page in one afternoon",
    },
  },
];

export function solution(slug) {
  return SOLUTIONS.find((item) => item.slug === slug) || null;
}
