// Practical guides for merchants, in both languages. Each answers a question a
// shop owner actually types into a search engine, gives advice that stands on
// its own without Vezano, and only then says which part of the product does
// the work. Dates are ISO and are the schema.org datePublished/dateModified.
//
// Shape per language: title (h1), metaTitle, description, intro (array of
// paragraphs), sections [{heading, paragraphs[], bullets?}], takeaway,
// related (solution slug), cta.

export const GUIDES = [
  {
    slug: "sell-during-outages",
    published: "2026-09-15",
    modified: "2026-09-15",
    minutes: 6,
    related: "offline-pos",
    ar: {
      title: "كيف تواصل البيع أثناء انقطاع الإنترنت والكهرباء",
      metaTitle: "كيف تواصل البيع أثناء انقطاع الإنترنت والكهرباء — دليل عملي للمحلات",
      description:
        "خطة عملية لمحل أو صيدلية أو مطعم كي لا يتوقف البيع حين تنقطع الشبكة أو الكهرباء: الأجهزة، الطاقة، البرنامج، والإجراء الذي يتبعه الكاشير.",
      intro: [
        "انقطاع الإنترنت في ساعة الذروة لا يوقف البيع فحسب، بل يوقف الطابور. الزبون الذي ينتظر خمس دقائق أمام كاشير معلّق يترك بضاعته ويخرج. والانقطاع في أسواقنا ليس حادثًا نادرًا يُخطَّط له مرة، بل حالة أسبوعية تحتاج إجراءً ثابتًا.",
        "هذا الدليل يرتّب ما تحتاجه في أربع طبقات: الطاقة، الاتصال، البرنامج، والإجراء البشري. الطبقات الثلاث الأولى تشتريها مرة، والرابعة تدرّب عليها فريقك مرة ثم تصبح عادة.",
      ],
      sections: [
        {
          heading: "١ · الطاقة قبل كل شيء",
          paragraphs: [
            "جهاز الكاشير هو آخر ما يجب أن ينطفئ في المحل. حاسوب محمول ببطارية سليمة أفضل من حاسوب مكتبي بلا وحدة طاقة احتياطية، لأن البطارية تمنحك ساعات لا دقائق. إن كان جهازك مكتبيًا فوحدة UPS صغيرة للكاشير والطابعة وجهاز الراوتر تكفي لتغطية الانقطاعات القصيرة.",
            "الطابعة الحرارية تستهلك طاقة أثناء الطباعة فقط، فلا تستبعدها من الـUPS. إيصال مطبوع أثناء الانقطاع هو ما يثبت البيع للزبون.",
          ],
          bullets: [
            "حاسوب محمول أو جهاز لوحي للكاشير، ببطارية تدوم ساعتين على الأقل",
            "UPS يغطي الطابعة والراوتر إن كان الجهاز مكتبيًا",
            "شاحن سيارة أو بنك طاقة احتياطي في الدرج، مجرّب لا جديد",
          ],
        },
        {
          heading: "٢ · لا تجعل الإنترنت شرطًا للبيع",
          paragraphs: [
            "الطبقة الثانية ليست إنترنت أفضل، بل برنامج لا يحتاجه لحظة البيع. أي نظام يطلب الخادم لكل فاتورة سيتوقف مهما كان اشتراكك. السؤال الذي تسأله لمزوّد البرنامج بسيط: لو فصلت كابل الشبكة الآن، هل أستطيع مسح باركود وإصدار فاتورة؟ إن كانت الإجابة تبدأ بـ«في الغالب» فالجواب لا.",
            "البرنامج المناسب يحتفظ بالمنتجات والأسعار على الجهاز، ويحفظ الفواتير محليًا أثناء الانقطاع، ويرسلها عند عودة الشبكة دون أن تُسجَّل مرتين. الشرط الأخير مهم: إعادة الإرسال بعد انقطاع في منتصف المزامنة يجب ألا تُنشئ فاتورة مكررة ولا تخصم المخزون مرتين.",
          ],
        },
        {
          heading: "٣ · اتصال احتياطي رخيص",
          paragraphs: [
            "شريحة بيانات في هاتف الكاشير، مع نقطة اتصال شخصية، تكفي كخط ثانٍ. لا تحتاج باقة كبيرة: المزامنة بعد الانقطاع بضع كيلوبايتات لكل فاتورة. المهم أن يكون الخط الثاني مجرّبًا قبل أن تحتاجه، لا أثناء الطابور.",
          ],
        },
        {
          heading: "٤ · الإجراء الذي يتبعه الكاشير",
          paragraphs: [
            "اكتب الإجراء في ورقة على الكاونتر. حين يظهر شريط «بلا اتصال» على الشاشة: واصل البيع كالمعتاد، لا تعد إدخال أي فاتورة سبق إصدارها، لا تُغلق البرنامج، وأخبر المسؤول إن استمر الانقطاع أكثر من ساعة. حين تعود الشبكة: انتظر رسالة اكتمال المزامنة قبل إغلاق الوردية، وراجع قائمة العمليات المعلّقة إن وُجدت.",
            "أكثر الأخطاء شيوعًا هو كاشير حسن النية يعيد إدخال فاتورة ظنًا أنها لم تُحفظ. البرنامج الجيد يمنع التكرار تقنيًا، لكن الإجراء المكتوب يمنع القلق أصلًا.",
          ],
        },
        {
          heading: "٥ · جرّب الانقطاع قبل أن يحدث",
          paragraphs: [
            "مرة في الشهر، افصل الإنترنت عمدًا لعشر دقائق في وقت هادئ. بِع ثلاث فواتير، أعد الاتصال، وتأكد أن الثلاث ظهرت في التقرير مرة واحدة. عشر دقائق شهريًا تشتري لك يقينًا في ساعة الذروة.",
          ],
        },
      ],
      takeaway:
        "الانقطاع ليس عذرًا لتوقف البيع إن كان الكاشير على بطارية، والبرنامج لا يحتاج الشبكة لحظة البيع، والفريق يعرف ماذا يفعل.",
      cta: "شاهد كيف يعمل كاشير فيزانو بلا اتصال",
    },
    en: {
      title: "How to keep selling through internet and power outages",
      metaTitle: "How to keep selling through internet and power outages — a practical guide for shops",
      description:
        "A working plan for a shop, pharmacy or restaurant so that sales do not stop when the network or the power goes: devices, power, software, and the routine the cashier follows.",
      intro: [
        "An internet outage at rush hour does not only stop sales; it stops the queue. A customer who waits five minutes at a frozen till leaves their goods and walks out. And in our markets an outage is not a rare event you plan for once; it is a weekly condition that needs a fixed routine.",
        "This guide arranges what you need in four layers: power, connectivity, software, and the human routine. You buy the first three once; the fourth you train your team on once and it becomes habit.",
      ],
      sections: [
        {
          heading: "1 · Power before anything else",
          paragraphs: [
            "The cashier's device should be the last thing in the shop to go dark. A laptop with a healthy battery beats a desktop with no backup unit, because a battery gives you hours, not minutes. If your till is a desktop, a small UPS covering the till, the printer and the router is enough for short outages.",
            "A thermal printer only draws power while printing, so do not leave it off the UPS. A receipt printed during the outage is what proves the sale to the customer.",
          ],
          bullets: [
            "A laptop or tablet at the till, with at least two hours of battery",
            "A UPS covering the printer and router if the till is a desktop",
            "A car charger or spare power bank in the drawer, tested, not new",
          ],
        },
        {
          heading: "2 · Do not make the internet a condition of selling",
          paragraphs: [
            "The second layer is not better internet; it is software that does not need it at the moment of sale. Any system that asks the server for every receipt will stop, whatever your subscription. The question to ask a vendor is simple: if I unplug the network cable now, can I scan a barcode and issue a receipt? If the answer begins with \"mostly\", the answer is no.",
            "The right software keeps products and prices on the device, saves receipts locally during the outage, and sends them when the network returns without recording them twice. That last condition matters: a retry after a drop in the middle of a sync must not create a duplicate receipt or deduct stock twice.",
          ],
        },
        {
          heading: "3 · A cheap backup connection",
          paragraphs: [
            "A data SIM in the cashier's phone, with a personal hotspot, is enough as a second line. You do not need a large plan: syncing after an outage is a few kilobytes per receipt. What matters is that the second line has been tried before you need it, not during the queue.",
          ],
        },
        {
          heading: "4 · The routine the cashier follows",
          paragraphs: [
            "Write the routine on a card at the counter. When the \"offline\" bar appears on screen: keep selling as usual, never re-enter a receipt that was already issued, do not close the program, and tell the manager if the outage lasts more than an hour. When the network returns: wait for the sync-complete message before closing the shift, and review the list of pending operations if there is one.",
            "The most common mistake is a well-meaning cashier re-entering a receipt in the belief it was not saved. Good software prevents the duplicate technically, but a written routine prevents the worry in the first place.",
          ],
        },
        {
          heading: "5 · Rehearse the outage before it happens",
          paragraphs: [
            "Once a month, deliberately disconnect the internet for ten minutes at a quiet time. Sell three receipts, reconnect, and confirm that all three appear in the report exactly once. Ten minutes a month buys you certainty at rush hour.",
          ],
        },
      ],
      takeaway:
        "An outage is no excuse for sales to stop, provided the till is on a battery, the software does not need the network at the moment of sale, and the team knows what to do.",
      cta: "See how the Vezano cashier works offline",
    },
  },
  {
    slug: "stock-count-without-closing",
    published: "2026-09-15",
    modified: "2026-09-15",
    minutes: 7,
    related: "inventory-expiry",
    ar: {
      title: "كيف تجرد مخزونك دون إغلاق المحل",
      metaTitle: "كيف تجرد المخزون دون إغلاق المحل — جرد دوري بالتناوب للمحلات والمستودعات",
      description:
        "طريقة الجرد الدوري بالتناوب: تعدّ جزءًا صغيرًا كل يوم بدل يوم إغلاق كامل، تعتمد الفروقات قبل تطبيقها، وتكتشف سبب الفرق بدل أن تصححه في صمت.",
      intro: [
        "الجرد السنوي يوم مرهق يُغلق فيه المحل، يُعدّ فيه كل شيء مرة واحدة، ويُصحَّح الرصيد ثم يُنسى السبب. بعد شهرين يعود الفرق كما كان لأن أحدًا لم يعرف من أين جاء.",
        "البديل الذي تعتمده سلاسل التجزئة الكبيرة متاح لأي محل: الجرد الدوري بالتناوب. تعدّ رفًا أو فئة واحدة كل يوم في وقت هادئ، فتغطي المحل كله خلال شهر دون أن تغلقه ساعة.",
      ],
      sections: [
        {
          heading: "١ · قسّم المخزون إلى مجموعات صغيرة",
          paragraphs: [
            "قسّم المحل بحسب ما يسهل عدّه في نصف ساعة: رف، ممر، أو فئة منتجات. الأصناف سريعة الحركة أو غالية الثمن تُعدّ أكثر من مرة في الشهر، والبطيئة الرخيصة مرة كل ثلاثة أشهر. القاعدة: ما يتحرك أكثر يُخطئ أكثر.",
          ],
          bullets: [
            "مجموعة واحدة في اليوم، في ساعة هادئة، بشخصين إن أمكن",
            "الأصناف ذات الصلاحية تُعدّ بالدفعة لا بالإجمالي",
            "ثبّت الترتيب على تقويم شهري، لا تترك الاختيار للمزاج",
          ],
        },
        {
          heading: "٢ · عدّ ما على الرف، لا ما في النظام",
          paragraphs: [
            "الخطأ الشائع أن يعدّ الموظف وهو ينظر إلى رقم النظام، فيبحث عن القطع التي تُطابقه. اطبع قائمة الأصناف بلا كميات، أو استخدم شاشة عدّ تُخفي رصيد النظام حتى ينتهي العدّ. العدّ الأعمى هو ما يكشف الفرق الحقيقي.",
          ],
        },
        {
          heading: "٣ · الفرق يُراجع قبل أن يُطبَّق",
          paragraphs: [
            "بعد العدّ تظهر قائمة الفروقات: ما زاد وما نقص وبكم. لا تُطبَّق التسوية تلقائيًا. المسؤول يراجع كل فرق: هل هو استلام لم يُسجَّل؟ بيع لم يُقيَّد؟ تلف لم يُوثَّق؟ كسر أو سرقة؟ التسوية تُعتمد بسبب مكتوب، فتصبح معلومة لا مجرد تصحيح.",
            "الفروقات المتكررة في صنف بعينه تدل على مشكلة إجراء: باركود مكرر، عبوة تُباع بالقطعة وتُستلم بالكرتونة، أو رف قريب من الباب. الجرد الدوري يكشف هذه الأنماط لأن العدّ يتكرر، والجرد السنوي لا يكشفها لأنه يحدث مرة.",
          ],
        },
        {
          heading: "٤ · البيع يستمر أثناء العدّ",
          paragraphs: [
            "لأن العدّ يستغرق نصف ساعة على جزء صغير، لا حاجة لإيقاف الكاشير. النظام الجيد يسجّل العدّ كلقطة مقابل رصيد لحظة بدء الجرد، فأي بيع يحدث أثناء العدّ لا يُحتسب فرقًا. إن كان برنامجك لا يفرّق بين الحالتين، عدّ الأصناف التي لا تُباع في تلك الساعة.",
          ],
        },
        {
          heading: "٥ · ما الذي تقيسه بعد ثلاثة أشهر",
          paragraphs: [
            "بعد دورة كاملة قِس شيئين: نسبة الأصناف التي طابق عدّها رصيد النظام، وقيمة الفروقات الصافية. الهدف أن تتحسن النسبة شهرًا بعد شهر، لا أن تصل إلى الكمال. حين تتجاوز 95% تكون قد حوّلت الجرد من يوم عذاب إلى عادة نصف ساعة.",
          ],
        },
      ],
      takeaway:
        "لا تُغلق المحل لتعرف ما فيه. عدّ جزءًا كل يوم، عدّه دون النظر إلى النظام، واعتمد الفرق بسبب مكتوب.",
      cta: "الجرد الدوري بفروقات معتمدة في فيزانو",
    },
    en: {
      title: "How to count your stock without closing the shop",
      metaTitle: "How to count stock without closing the shop — cycle counting for shops and warehouses",
      description:
        "The cycle-counting method: count a small part every day instead of a full closure day, approve variances before applying them, and find the cause of a difference instead of correcting it silently.",
      intro: [
        "The annual stocktake is an exhausting day: the shop closes, everything is counted once, the balance is corrected and the cause is forgotten. Two months later the difference is back, because nobody learned where it came from.",
        "The alternative the large retail chains use is available to any shop: cycle counting. You count one shelf or one category each day at a quiet time, covering the whole shop within a month without closing for an hour.",
      ],
      sections: [
        {
          heading: "1 · Split the stock into small groups",
          paragraphs: [
            "Divide the shop by what can be counted in half an hour: a shelf, an aisle, or a product category. Fast-moving or expensive items are counted more than once a month; slow, cheap ones once a quarter. The rule: what moves more, errs more.",
          ],
          bullets: [
            "One group per day, at a quiet hour, with two people if possible",
            "Items with expiry dates are counted by batch, not in total",
            "Fix the order on a monthly calendar; do not leave the choice to mood",
          ],
        },
        {
          heading: "2 · Count what is on the shelf, not what is in the system",
          paragraphs: [
            "The common mistake is an employee counting while looking at the system's number, and searching for the pieces that match it. Print the item list without quantities, or use a count screen that hides the system balance until the count is done. A blind count is what reveals the real difference.",
          ],
        },
        {
          heading: "3 · Variances are reviewed before they are applied",
          paragraphs: [
            "After the count comes a list of variances: what is over, what is short, and by how much. The adjustment is not applied automatically. A manager reviews each difference: a receipt that was not recorded? A sale that was not posted? Spoilage that was not documented? Breakage or theft? The adjustment is approved with a written reason, so it becomes information rather than a mere correction.",
            "Repeated variances on the same item point to a process problem: a duplicated barcode, a pack sold by the piece and received by the carton, or a shelf near the door. Cycle counting exposes these patterns because the count repeats; the annual stocktake does not, because it happens once.",
          ],
        },
        {
          heading: "4 · Selling continues during the count",
          paragraphs: [
            "Because a count takes half an hour on a small section, there is no need to stop the till. Good software records the count as a snapshot against the balance at the moment the count began, so a sale made during the count is not treated as a variance. If your software does not distinguish the two, count the items that are not selling at that hour.",
          ],
        },
        {
          heading: "5 · What to measure after three months",
          paragraphs: [
            "After a full cycle, measure two things: the share of items whose count matched the system balance, and the net value of the variances. The aim is for the share to improve month on month, not to reach perfection. Once it passes 95% you have turned the stocktake from a day of misery into a half-hour habit.",
          ],
        },
      ],
      takeaway:
        "Do not close the shop to learn what is in it. Count a part every day, count it without looking at the system, and approve the difference with a written reason.",
      cta: "Periodic counts with approved variances in Vezano",
    },
  },
  {
    slug: "collect-customer-debts",
    published: "2026-09-15",
    modified: "2026-09-15",
    minutes: 6,
    related: "customer-debts",
    ar: {
      title: "كيف تحصّل ديون العملاء دون أن تخسرهم",
      metaTitle: "كيف تحصّل ديون العملاء دون أن تخسرهم — نظام تحصيل للمحلات وتجار الجملة",
      description:
        "نظام تحصيل بسيط لتاجر التجزئة والجملة: حد ائتمان لكل عميل، كشف حساب شهري بدل المطالبة الشفهية، تقسيم الديون بعمرها، وترتيب الاتصال بمن تأخر.",
      intro: [
        "البيع الآجل يجلب العميل ويُبقيه، لكن الدين الذي لا يُتابع يتحول من خدمة إلى خسارة ثم إلى خصومة. معظم التجار لا يخسرون بسبب عميل سيئ النية، بل بسبب دين نُسي شهرين ثم طُلب فجأة بنبرة اتهام.",
        "التحصيل الجيد ليس شدة ولا لينًا، بل انتظام. حين يعرف العميل أن كشف حسابه يصل أول كل شهر، وأن الرصيد لا يُختلف عليه لأنه موثّق بفواتيره، يدفع في موعده لأن هذا هو المعتاد لا لأنه طُولب.",
      ],
      sections: [
        {
          heading: "١ · حد ائتمان لكل عميل قبل أول فاتورة آجلة",
          paragraphs: [
            "لا تمنح الدين لمن لا تعرف طاقته. ابدأ بحد صغير يعادل مشتريات أسبوعين، وارفعه مع كل دورة سداد منتظمة. الحد ليس عدم ثقة، بل إطار يحمي الطرفين. الكاشير الذي يعرف الحد لا يحتاج أن يسأل المالك عند كل عملية.",
          ],
        },
        {
          heading: "٢ · كشف الحساب بدل المطالبة",
          paragraphs: [
            "المطالبة الشفهية تفتح جدالًا: كم؟ منذ متى؟ أليس هذا مدفوعًا؟ كشف الحساب يغلقه. قائمة بالفواتير والدفعات والمرتجعات بالتاريخ والرقم، تصل للعميل أول كل شهر على واتساب أو مطبوعة مع أول توصيلة. من يرى الكشف يدفع دون أن يُطلب منه، ومن يعترض يعترض على رقم محدد يمكن التحقق منه.",
          ],
          bullets: [
            "كشف حساب شهري ثابت الموعد لكل عميل له رصيد",
            "كل دفعة بإيصال مرقّم، وكل مرتجع بإشعار دائن",
            "لا تصحيح باليد على الرصيد، بل قيد موثّق بسبب",
          ],
        },
        {
          heading: "٣ · قسّم الديون بعمرها لا بحجمها",
          paragraphs: [
            "الدين الكبير الحديث أقل خطرًا من الدين الصغير القديم. رتّب الأرصدة في أربع فئات: أقل من 30 يومًا، 30 إلى 60، 60 إلى 90، وأكثر من 90. الفئة الأولى لا تحتاج شيئًا سوى الكشف الشهري. الثانية تحتاج رسالة ودّية. الثالثة مكالمة. الرابعة إيقاف البيع الآجل حتى تسوية جزئية.",
            "هذا التقسيم يحوّل التحصيل من مهمة عامة مزعجة إلى قائمة قصيرة محددة كل أسبوع: من انتقل إلى الفئة الثانية أو الثالثة هذا الأسبوع؟ هؤلاء فقط من تتصل بهم.",
          ],
        },
        {
          heading: "٤ · اقبل الدفعة الجزئية دائمًا",
          paragraphs: [
            "العميل الذي يدفع نصف المبلغ يُبقي العلاقة حية ويثبت النية. سجّل الدفعة الجزئية فورًا بإيصال، واترك الباقي في الفئة العمرية نفسها بتاريخ الفاتورة الأصلي، فلا يُعاد عدّ الدين من الصفر. رفض الدفعة الجزئية انتظارًا للكامل يخسر الاثنين غالبًا.",
          ],
        },
        {
          heading: "٥ · افصل بين من يسجّل المال ومن يعتمده",
          paragraphs: [
            "في المحل الصغير يسجّل الكاشير الدفعة ويؤكدها المالك آخر اليوم. في الأكبر تُعتمد الدفعات التي تتجاوز حدًا معينًا من مسؤول قبل أن تُخصم من الرصيد. الفصل ليس اتهامًا لأحد، بل الطريقة الوحيدة التي تجعل الرصيد على الشاشة رقمًا يُعتمد عليه أمام العميل.",
          ],
        },
      ],
      takeaway:
        "حد ائتمان واضح، كشف حساب شهري في موعده، وتقسيم بالعمر يخبرك بمن تتصل هذا الأسبوع. التحصيل انتظام لا مواجهة.",
      cta: "دفتر الديون وكشوف الحساب وأعمار الديون في فيزانو",
    },
    en: {
      title: "How to collect customer debts without losing the customers",
      metaTitle: "How to collect customer debts without losing the customers — a collection routine for retailers and wholesalers",
      description:
        "A simple collection routine for retail and wholesale: a credit limit per customer, a monthly statement instead of a verbal demand, debts sorted by age, and a short list of who to call.",
      intro: [
        "Selling on credit wins the customer and keeps them, but a debt that is not followed up turns from a service into a loss and then into a quarrel. Most merchants do not lose because of a customer acting in bad faith; they lose because a debt was forgotten for two months and then suddenly demanded in an accusing tone.",
        "Good collection is neither harsh nor soft; it is regular. When a customer knows their statement arrives on the first of every month, and that the balance is not up for debate because it is backed by their own invoices, they pay on time because that is the norm, not because they were chased.",
      ],
      sections: [
        {
          heading: "1 · A credit limit per customer before the first credit invoice",
          paragraphs: [
            "Do not extend credit to someone whose capacity you do not know. Start with a small limit equal to two weeks of purchases and raise it with every regular repayment cycle. The limit is not distrust; it is a frame that protects both sides. A cashier who knows the limit does not need to ask the owner at every sale.",
          ],
        },
        {
          heading: "2 · A statement instead of a demand",
          paragraphs: [
            "A verbal demand opens an argument: how much? Since when? Wasn't that paid? A statement closes it. A list of invoices, payments and returns with dates and numbers, reaching the customer on the first of each month by WhatsApp or printed with the first delivery. Those who see the statement pay without being asked, and those who object object to a specific figure that can be checked.",
          ],
          bullets: [
            "A monthly statement on a fixed date for every customer with a balance",
            "Every payment on a numbered receipt, every return on a credit note",
            "No hand-edits to the balance; a documented entry with a reason",
          ],
        },
        {
          heading: "3 · Sort debts by age, not by size",
          paragraphs: [
            "A large recent debt is less risky than a small old one. Arrange balances in four bands: under 30 days, 30 to 60, 60 to 90, and over 90. The first band needs nothing but the monthly statement. The second needs a friendly message. The third a phone call. The fourth a pause on credit sales until a partial settlement.",
            "This banding turns collection from a vague, unpleasant chore into a short, specific weekly list: who moved into the second or third band this week? Those are the only people you call.",
          ],
        },
        {
          heading: "4 · Always accept a partial payment",
          paragraphs: [
            "A customer who pays half keeps the relationship alive and proves intent. Record the partial payment immediately with a receipt, and leave the remainder in the same age band under the original invoice date, so the debt is not counted from zero again. Refusing a partial payment while waiting for the full amount usually loses both.",
          ],
        },
        {
          heading: "5 · Separate who records money from who approves it",
          paragraphs: [
            "In a small shop the cashier records the payment and the owner confirms it at the end of the day. In a larger one, payments above a set threshold are approved by a manager before they reduce the balance. The separation accuses nobody; it is the only way the balance on the screen becomes a figure you can stand behind in front of the customer.",
          ],
        },
      ],
      takeaway:
        "A clear credit limit, a monthly statement on time, and age bands that tell you who to call this week. Collection is regularity, not confrontation.",
      cta: "Debt ledger, statements and ageing in Vezano",
    },
  },
];

export function guide(slug) {
  return GUIDES.find((item) => item.slug === slug) || null;
}
