# ORCA Max Mouny — تنفيذ القسم 22

هذا المستند يوثق تنفيذ «الحلقة الخارجية للمعايرة الذاتية المستمرة والذاكرة المناعية العابرة للنظام». التنفيذ امتداد للقسمين 20 و21 ولا يعدّل حدود المخاطر أو صلاحيات السحب أو فصل الصلاحيات. **لا تمنح مكونات القسم 22 رأس مالًا حيًا ولا تملك صلاحية Live مباشرة.**

## مطابقة المتطلبات

| البند | التنفيذ الفعلي | الضابط والحد الواقعي |
|---|---|---|
| 22.1.1 المدى الآمن | `SafeParameter` و`DEFAULT_SAFE_PARAMETERS` في `analytics/calibration22.py` | كل معلمة لها حد أدنى وأقصى ثابتان. تغيير المدى يرفض تلقائيًا ما لم تُستدعَ مراجعة ربع سنوية مكتوبة، ولا يستطيع النموذج إعادة تعريف المدى. |
| 22.1.2 التحسين البايزي | `BayesianCalibrator` يستخدم Gaussian Process فعليًا عند توفر ملاحظتين أو أكثر، مع prior محافظ قبل ذلك | الاقتراحات review-only؛ لا تعديل مباشر لسياسة الخطر أو الأوامر. |
| 22.1.3 Bandit-over-Bandit | نافذة متحركة `window_size` لإعادة ملاءمة النموذج على أحدث ملاحظات، مع cadence لا يتجاوز أسبوعًا | لا توجد دعوى تفوق أداء؛ هذا تنفيذ آلية اقتراح فقط. |
| 22.1.4 Contextual Thompson Sampling | `thompson_discrete` يحافظ على posterior منفصل للسياق السوقي عند اختيار المعلمات المنفصلة | يستخدم السياق كذاكرة اختيار، ولا يتجاوز CPCV/PBO/DSR أو shadow. |
| 22.1.5 بوابات القسم 20 | `record_calibration` لا يضع `gates_passed=True` إلا بعد CPCV وPBO وDSR وshadow | حتى عند اجتيازها يبقى `execution_eligible=False` ويلزم المسار القائم للمراجعة. |
| 22.1.6 الدورية | `cadence_days` مقيد برمجيًا إلى أسبوع كحد أقصى للاقتراح | لا توجد جدولة دائمة أو تشغيل على Windows من داخل هذه البيئة. |
| 22.1.7 التدقيق | `AuditLog` يسجل كل اقتراح ونتيجة ورفض وكاشف مناعي | لا تُسجل أسرار أو مفاتيح؛ سجل الاختبار الواقعي مؤقت خارج المستودع. |
| 22.2.1 ملف Self | `ImmuneMemory.add_self` يجمع متجهات الخصائص عبر الأزواج والاستراتيجيات داخل الذاكرة المشتركة | التحقق الواقعي الحالي استخدم متجهات عوائد/تقلب/Z-score كتمرين proxy، وليس سجلات صفقات مؤكدة. |
| 22.2.2 Antigen | `classify_antigen` يعلّم الخسارة التي تتجاوز risk budget أو الخسارة مع edge غير موجب | لا تُقدّم labels المشتقة من الشموع كأنها trade outcomes. |
| 22.2.3 Negative Selection وClonal Selection | توليد كاشف خارج Self، تأكيد hit، زيادة الشدة، واستنساخ/تحوير الكاشف المؤكد | لا حذف للكاشف المؤكد؛ الإيجابيات الكاذبة مقياس قبول ويظل التحقق الحقيقي من صفقات متعددة الأزواج مطلوبًا. |
| 22.2.4 الفحص قبل الدخول | `screen` يرجع affinity و`size_multiplier` و`reject` | التأثير أحادي الاتجاه: تخفيض أو رفض فقط، ولا يمكنه زيادة الحجم. |
| 22.2.5 المشاركة العابرة للنظام | الذاكرة في `Section22Layer` مشتركة، و`cross_system_sharing_latency_cycles=0` عند إنشاء الكاشف | الرقم يثبت مشاركة الذاكرة داخل العملية، وليس زمن شبكة بين عمليات أو منصات مستقلة. |
| 22.2.6 الاضمحلال | `decay_cycle` يخفض الشدة تدريجيًا بعد shadow pass ولا يحذف الكاشف، مع إعادة تنشيط ممكنة | لا تخفيف فوري لمرة واحدة؛ لا توجد إزالة نهائية للكاشف المؤكد. |
| 22.2.7 عدوى المنصات | `network_adjust` يرفع الشدة عند `contagion_affected=True` | لا توجد آلية زيادة تعرض. |
| 22.2.8 الفرق عن drift | الذاكرة تحفظ بصمة فشل مؤكدة، بينما `explainability.py` يرسل drift إلى مراجعة القسم 20 | المخرجان متكاملان وليسا آلية واحدة. |
| 22.3 الدمج | `Section20Layer.on_section22_trade_closed` هو نقطة التكامل الوحيدة بعد إغلاق الصفقة، قبل بقية تحديثات التحليل | لا يملك القسم 22 قرار تقاعد أو ترقية مستقلًا؛ يغذي القسم 20 فقط. |
| 22.4 الحوكمة | Kill-Switch يوقف الاقتراح والفحص والتحديث، و`Section22Layer` review-only | حدود الخطر الثابتة، حدود الخسارة، السحب، الصلاحيات، والفصل الأمني لا تتغير. |
| 22.5 معايير الأثر | توجد واجهات metrics لـTP/FP/precision/retained/latency، وتسجل المقارنة المطلوبة كـnot performed عندما لا توجد استراتيجية parameterized مطابقة | لا يُعتمد أي تحسن، ولا تُنقل نتيجة proxy إلى Live. يلزم لاحقًا ربط evaluator حقيقي بنفس استراتيجية/زوج ونفس نافذة البيانات. |
| 22.6 الإفصاح | التقرير يصرح بالمصدر والـproxy والطلبات والمفاتيح والحدود | لا توجد أرقام ربح أو Win Rate أو جاهزية Live من القسم 22. |

## تحقق واقعي في 26 أغسطس 2026

شُغّل `scripts/orca_section22_real.py` باستخدام **1000 شمعة BTC/USDT، 1h** من REST العام لـBinance، من 15 يوليو 2026 13:00 UTC إلى 26 أغسطس 2026 04:00 UTC. لم يُستخدم مفتاح ولم يُرسل أمر.

| القياس | النتيجة | تفسيره |
|---|---:|---|
| اقتراح معايرة | 1 | اقتراح داخل المدى الآمن، review-only |
| التنفيذ المؤهل | 0 | ثابت برمجيًا في القسم 22 |
| السياق السوقي | quiet | ناتج كاشف النظام الحالي |
| ملاحظات الذاكرة | 975 | تمرين خصائص على العوائد، وليس سجلات صفقات |
| Antigens في تمرين proxy | 44 | تعريف تشخيصي على عوائد الشموع |
| الكاشفات المحتفظ بها | 43 | لا حذف نهائي |
| أحداث التدقيق | 523 | في سجل مؤقت أثناء التحقق |
| نتيجة المعايرة | مرفوضة | `cpcv_pass=False`, `pbo=1.0`, `dsr=-1.0`, `shadow_pass=False` في تجربة الحوكمة، لذلك لا اعتماد |
| الأوامر | 0 | لا Paper order ولا Sandbox ولا Live order |
| المفاتيح | 0 | لم تُستخدم مفاتيح |

الـTP/FP في هذا التقرير لا يُستخدم كمعيار اعتماد؛ لأن التمرين لم يملك سجل صفقات مقبول/فاشل بخصائص وقت الدخول، بل استخدم عوائد OHLCV عامة كـproxy معلن. كما أن مقارنة المعايرة الأسبوعية بالمعايرة اليدوية الربع سنوية لم تُنفذ بعد لعدم وجود evaluator موحد موصول بهذه الثوابت داخل استراتيجية parameterized بنفس نافذة البيانات. لذلك لا توجد دعوى تحسن.

## المراجع البحثية

اختير Gaussian Process/Bayesian optimization باعتباره مسارًا موثقًا لمشكلات التقييم المكلف والصاخب، مع الاستناد إلى أعمال Bergstra وSnoek [1] [2]. استُخدمت فكرة الانتقاء السلبي لنظام المناعة من Forrest وزملائها، وفكرة الانتقاء النسيلي من de Castro وVon Zuben [3] [4]. هذه المراجع تبرر اختيار النمط الخوارزمي، لكنها **لا تثبت أداء ORCA Max Mouny** ولا تغني عن تحقق CPCV/PBO/DSR وshadow على بيانات تداول فعلية.

## المراجع

1. [Bergstra et al. — Algorithms for Hyper-Parameter Optimization](https://papers.nips.cc/paper/4443-algorithms-for-hyper-parameter-optimization)
2. [Snoek et al. — Practical Bayesian Optimization of Machine Learning Algorithms](https://papers.nips.cc/paper/4522-practical-bayesian-optimization-of-machine-learning-algorithms)
3. [Forrest et al. — Self-Nonself Discrimination and Detection of Intrusions](https://www.cs.unm.edu/~immsec/publications/forrest-1994.pdf)
4. [de Castro and Von Zuben — Learning and Optimization Using the Clonal Selection Principle](https://www.cs.unm.edu/~immsec/publications/decastro-2002.pdf)
5. [Binance Spot API — Kline/Candlestick Data](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints#klinecandlestick-data)
