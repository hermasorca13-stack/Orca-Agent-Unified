# ORCA Max Mouny

## الحالة التنفيذية

هذا المجلد يضيف إلى مستودع Orca-Agent-Unified نواة تداول كمية متعددة الاستراتيجيات باسم **ORCA Max Mouny** مع شعار حوت الأوركا. النواة قابلة للتشغيل الآن في وضع **Paper**، وتحتوي موصلًا فعليًا اختياريًا عبر CCXT لبيئة sandbox أو API حقيقي عند إدخال الاعتمادات في بيئة التشغيل فقط.

> الوضع الافتراضي هو `paper`. لا توجد مفاتيح حقيقية مضمّنة في المصدر، ولا يسمح التحقق الابتدائي بتفعيل صلاحية السحب.

## مسارا التشغيل

| المسار | النتيجة | المتطلبات | التكلفة/القيود |
|---|---|---|---|
| تشغيل مستقل على خادم دائم | تشغيل 24/7، WebSocket، REST، سجلات محلية، وخدمة مراقبة | Python، مساحة دائمة، إدارة systemd أو Docker، وموارد الخادم المناسب | تكلفة الخادم الخارجي حسب المزود؛ مناسب لمواصفات 16 نواة و64GB المطلوبة |
| تشغيل مُدار خفيف | واجهة إعداد ومهام خلفية على بيئة مُدارة | اعتماد بيئة مُدارة بحد 1 vCPU و512MB | يبدأ مجانًا، والاستضافة المحجوزة تصل إلى نحو 37.50 دولارًا شهريًا عند الاستهلاك الكامل 24/7، مع خصم 10 دولارات الاستخدام المجاني، إضافة إلى النقل والتخزين حسب الاستخدام؛ غير مناسب لتدريب TensorFlow أو 17 منصة عالية التردد |

المشروع الحالي مستقل عن المسار، ولذلك يمكن تشغيله محليًا أو على خادم دائم دون إعادة كتابة النواة.

## الأوضاع

`paper` يحاكي دفتر الأوامر والأرصدة والتنفيذ والرسوم محليًا دون اتصال بمنصة. `sandbox` يستخدم مفاتيح بيئة اختبار المنصة ويستدعي الموصل الخارجي مع تفعيل sandbox قبل أول طلب. `live` يستخدم API الحقيقي فقط عند وجود اعتمادات صريحة لكل منصة مفعّلة، مع رفض الإقلاع إذا كانت الاعتمادات مفقودة أو كانت صلاحية السحب مفعلة.

تُحفظ الأسرار في متغيرات البيئة أو مدير أسرار خارجي. ملف `.env.orca.example` يوضح جميع الحقول ويترك مفاتيح التداول الحقيقي فارغة. لا تُسجّل المفاتيح في `audit.jsonl`؛ طبقة التدقيق تطبق إخفاءً تلقائيًا على أسماء الحقول الحساسة.

## المكونات

| المكوّن | الوظيفة |
|---|---|
| `trading_bot/models.py` | نماذج السوق والأوامر والتنفيذات والإشارات والمخاطر |
| `trading_bot/config/settings.py` | إعدادات موحدة وتحقق fail-closed من الحدود والصلاحيات |
| `trading_bot/adapters/paper.py` | تنفيذ Paper محلي حقيقي لأغراض التطوير والاختبار |
| `trading_bot/adapters/ccxt_adapter.py` | موصل اختياري لـCCXT للـsandbox/live |
| `trading_bot/data/providers.py` | بيانات Binance العامة عبر REST وWebSocket مع قياس latency |
| `trading_bot/data/context.py` | Fear & Greed وسعر BTC ومتوسط 200 أسبوع من مصادر عامة |
| `trading_bot/data/hub.py` | تنسيق اللقطات وفحص freshness والبطء |
| `trading_bot/analytics/indicators.py` | EMA، RSI، Stochastic RSI، ATR، Heikin Ashi، Elder Weight Oscillator، Beta |
| `trading_bot/analytics/statistics.py` | OLS، اختبار ADF-style، الثبات، التكامل المشترك، الارتباط، والـZ-Score |
| `trading_bot/strategies/technical.py` | نموذج إشارة الزخم والفلاتر الفنية مع ثلاث تأكيدات على الأقل |
| `trading_bot/strategies/arbitrage.py` | Cross-Exchange Arbitrage وStatistical/Pair Arbitrage بعد التكاليف |
| `trading_bot/risk/gates.py` | بوابات التكلفة والبيانات والسيولة والأحداث والهامش والخسارة |
| `trading_bot/risk/kill_switch.py` | إيقاف طارئ دائم عند فشل البيانات أو API أو الحدود |
| `trading_bot/risk/policy.py` | احتياطي المحفظة، التعرض، حظر المارتينجال والمراكز غير المحوطة |
| `trading_bot/monitoring.py` | مراقبة تشغيلية تربط حالات الفشل بـKill-Switch |
| `trading_bot/storage/market_store.py` | تخزين SQLite لبيانات السوق وقرارات النظام |
| `trading_bot/execution/engine.py` | دخول متدرج، تحوط شبه متزامن، وخروج مرحلي |
| `trading_bot/storage/audit.py` | سجل JSONL دائم لكل قرار وأمر وتنفيذ وسبب رفض |
| `trading_bot/analytics/backtest.py` | اختبار رجعي زمني بلا look-ahead مع رسوم وانزلاق |
| `trading_bot/analytics/validation.py` | OOS، Walk-Forward، Monte Carlo، واختبارات ضغط |
| `trading_bot/analytics/model_registry.py` | تدريب مرحلي واعتماد نموذج بإقرار مراجع دون تغيير المخاطر |
| `trading_bot/analytics/meta_labeling.py` | Triple-Barrier وMeta-Labeling احتمالي بالـATR |
| `trading_bot/analytics/regime.py` | كشف quiet/transitional/turbulent وتكييف العتبات والأوزان |
| `trading_bot/analytics/weighting.py` | ترجيح تراكمي بسقف وتغيير تدريجي |
| `trading_bot/analytics/bias_control.py` | CPCV مع Purging/Embargo وPBO وDeflated Sharpe |
| `trading_bot/analytics/execution_feedback.py` | تعلم الانزلاق وترتيب المنصات وتعليق المتدهور |
| `trading_bot/analytics/shadow.py` | بوابة التداول الظلي وكشف الانحراف |
| `trading_bot/analytics/retirement.py` | تقاعد تشغيلي تراكمي قابل لإعادة التفعيل |
| `trading_bot/risk/kelly.py` | Fractional Kelly مقيد بسقف المخاطر والتقلب |
| `trading_bot/analytics/alpha_discovery.py` | اكتشاف مرشحي alpha بتعبيرات مقيدة، review-only |
| `trading_bot/analytics/causal.py` | Granger-style وTransfer Entropy وآلية اقتصادية معلنة |
| `trading_bot/analytics/online_experts.py` | مزيج خبراء Beta online وكشف نقاط التحول |
| `trading_bot/analytics/stress_generator.py` | block bootstrap وضغط هبوطي محافظ؛ ليس TimeGAN |
| `trading_bot/analytics/tail_risk.py` | CVaR وEVT tail diagnostics |
| `trading_bot/analytics/contagion.py` | correlation/centrality وعدوى المنصات وتقليل التعرض |
| `trading_bot/analytics/explainability.py` | permutation importance وPSI/JSD drift |
| `trading_bot/analytics/governance21.py` | مراجعة مرشحين، Kill-Switch، ومنع Live authority |
| `docs/SECTION20_IMPLEMENTATION.md` | مطابقة بنود القسم 20 ونتائج التحقق |
| `docs/SECTION21_IMPLEMENTATION.md` | مطابقة بنود القسم 21 ونتيجة التحقق الواقعي |
| `trading_bot/analytics/calibration22.py` | معايرة Bayesian/GP مقيدة ومدخلات Thompson سياقية، review-only |
| `trading_bot/analytics/immune_memory22.py` | ذاكرة مناعية مشتركة، negative selection، clonal refinement، decay |
| `trading_bot/analytics/section22.py` | منسق القسم 22 مع AuditLog وKill-Switch |
| `docs/SECTION22_IMPLEMENTATION.md` | مطابقة بنود القسم 22 ونتيجة التحقق الواقعي |
| `trading_bot/analytics/infrastructure23.py` | ميزانيات الحوسبة، فصل العقد، ومراقبة latency |
| `trading_bot/analytics/execution_quality23.py` | VPIN، حماية market making، AC scheduler، SOR، وحارس MEV |
| `trading_bot/analytics/derivatives23.py` | Greeks وحد Vega وIV surface diagnostics |
| `trading_bot/analytics/capacity23.py` | السعة، الأثر، alpha decay، والازدحام |
| `trading_bot/analytics/data_quality23.py` | تحقق مصادر متعددة وأرشفة point-in-time |
| `trading_bot/analytics/rollout23.py` | pilot ramp وcode review/canary/rollback |
| `trading_bot/analytics/compliance23.py` | legal hold، MiCA check، tax ledger، continuity، insurance، benchmark |
| `trading_bot/analytics/section23.py` | المنسق الموحد لقيود الواقع والتنفيذ والقانون |
| `docs/SECTION23_IMPLEMENTATION.md` | مطابقة بنود القسم 23 ونتيجة التحقق الواقعي |
| `assets/orca_max_mouny/orca-whale.svg` | شعار حوت الأوركا بصيغة SVG |
| `deploy/` | قالب Docker/systemd ونشر مستقل للمضيف الدائم |
| `trading_bot/analytics/public_sources23.py` | Binance/Coinbase/Kraken read-only cross-source adapters |
| `trading_bot/ops/readiness.py` | فحص Paper/Sandbox/Live والأسرار والسحب دون كشف القيم |
| `deploy/windows/readiness.ps1` | فحص Windows للجاهزية والمصادر العامة |
| `scripts/orca_cross_source_real.py` | تقرير Binance/Coinbase/Kraken العام مع بوابة latency |
| `docs/cross_source_report_2026-08-26.json` | نتيجة فحص المصادر العامة الأخير |
| `trading_bot/analytics/section24.py` | الجلسات الزمنية والمكانية، GDELT، اللغة، الأثر على العملات، وقفل الأحداث |
| `trading_bot/analytics/rss24.py` | RSS عام متعدد اللغات كمسار fallback معلن |
| `scripts/orca_section24_real.py` | تحقق القسم 24 ببيانات أحداث وجلسات عامة دون أوامر |
| `docs/SECTION24_IMPLEMENTATION.md` | مطابقة متطلبات القسم 24 ونتيجة التحقق الواقعي |
| `trading_bot/ops/capability_catalog.py` | سجل قدرات قائم على الدليل ومنع التكرار، غير تنفيذي |
| `docs/CAPABILITY_CATALOG.md` | نتائج مقارنة ملف TypeScript بما هو موجود واستبعاد العناصر المكررة |

## التشغيل

```bash
cd /home/ubuntu/Orca-Agent-Unified
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.orca.example .env.orca
set -a; . .env.orca; set +a
python3 run_orca_max_mouny.py status
python3 run_orca_max_mouny.py paper-demo
PYTHONPATH=. python3 -m trading_bot.app paper-history
PYTHONPATH=. python3 scripts/orca_meta_label_real.py
PYTHONPATH=. python3 scripts/orca_optimize_real.py
PYTHONPATH=. python3 scripts/orca_section21_real.py
PYTHONPATH=. python3 scripts/orca_section22_real.py
PYTHONPATH=. python3 scripts/orca_section23_real.py
PYTHONPATH=. python3 scripts/orca_cross_source_real.py
PYTHONPATH=. python3 -m trading_bot.ops.readiness --json
PYTHONPATH=. python3 scripts/orca_section24_real.py
PYTHONPATH=. python3 -m trading_bot.ops.readiness --json
python3 -m trading_bot.cli.doctor
pytest -q tests/trading_bot
```

لتشغيل sandbox، أنشئ مفاتيح من شبكة الاختبار في المنصة نفسها، ثم اضبط `ORCA_TRADING_MODE=sandbox` و`ORCA_ACTIVE_EXCHANGES=binance` واملأ متغيرات Binance من خارج Git. لا تُستخدم مفاتيح الإنتاج في sandbox، ولا تُفعّل `ORCA_*_ENABLE_WITHDRAW`.

لتفعيل live، يجب أولًا إجراء مراجعة مستقلة للإعدادات والاعتماد والحدود، ثم ضبط `ORCA_TRADING_MODE=live` و`ORCA_ACTIVE_EXCHANGES` وإدخال الاعتمادات في مدير أسرار أو متغيرات بيئة خارج المستودع. البرنامج لا ينفّذ صفقة من تلقاء نفسه عند الإقلاع؛ يبدأ التشغيل من خلال دورة الإشارة والتنفيذ التي يجب ربطها بمصدر بيانات حقيقي بعد اختبار sandbox.

## تسلسل التشغيل الموحّد

يبدأ النظام بتحميل الإعدادات والتحقق من حدود المخاطر، ثم ينشئ موصلات السوق ويجمع الأسعار، ويحسب المؤشرات والفروق والتمويل والسيولة، ويجري الاختبارات الإحصائية اللازمة، ثم يمرر الإشارة إلى بوابة التكاليف والمخاطر. عند الموافقة، يحدد الحجم عكسيًا مع التقلب، وينفذ الدخول على شرائح صغيرة، ويعيد حساب الحياد والتعرض، ثم يدير الخروج المرحلي والتوقف الطارئ ويكتب كل مرحلة في سجل UTC.

## فحوص القبول

قبل أي انتقال من Paper إلى sandbox يجب أن ينجح اختبار رجعي لا يقل عن 200 صفقة تاريخية، واختبار خارج العينة، واختبار Walk-Forward، واختبار Monte Carlo، واختبارات انهيار السعر واتساع السبريد وتوقف المنصة وفشل API وارتفاع التمويل وفشل التحوط. يجب تسجيل النتائج قبل الرسوم وبعد الرسوم والتمويل والانزلاق والتكاليف الأخرى، وقياس Sharpe وProfit Factor وMax Drawdown وWin Rate وSortino وCalmar.

معايير القبول المستهدفة من وثيقة المتطلبات هي Sharpe أكبر من 2.0، وProfit Factor أكبر من 2.0، وMax Drawdown أقل من 20%، وWin Rate أكبر من 50%، مع اعتماد السجل الكامل وجميع الحسابات والإيداعات والسحوبات والرسوم والتمويل والانزلاق والتصفية عند احتساب الأداء. تحديث نموذج الإشارة يتم في مساحة staging ثم لا يصبح معتمدًا إلا بعد `approve(reviewer=...)`؛ ولا يملك سجل النموذج أي مسار لتعديل حدود المخاطر.

تقرير البيانات الحقيقية المحفوظ في [`validation_report_2026-08-26.json`](validation_report_2026-08-26.json) استخدم 1000 شمعة BTC/USDT على إطار الساعة من Binance، وطبّق OOS و13 نافذة Walk-Forward واختبارات رسوم وانزلاق وMonte Carlo. تقرير التحسين المحفوظ في [`optimization_report_2026-08-26.json`](optimization_report_2026-08-26.json) بحث في معاملات المتوسطات وعتبات الإشارة على العينة الداخلية فقط ثم اختبرها خارج العينة؛ أفضل SMA حقق OOS Win Rate = 44.78% وProfit Factor = 1.024 وSharpe = 0.118، بينما نتيجة التقاطع ذات Win Rate = 100% اعتمدت على صفقتين فقط خارج العينة ولذلك رُفضت ببوابة الحد الأدنى. النتيجة الحالية **مرفوضة** لبوابة القبول، ولا يُسمح باعتبار أي من هذه الاستراتيجيات معتمدة أو نقلها إلى تداول حقيقي.

### تحقق القسم 21

شغّل `scripts/orca_section21_real.py` على 1000 شمعة BTC/USDT عامة من Binance. نتج 16 مرشحًا عازلًا، صفر مؤهل للتنفيذ، CVaR 95% = 0.7544%، وأسوأ سحب في 24 سيناريو ضغط = 32.3411%. ظهر تحذير PSI = 0.2656، ورفضت الحوكمة المرشح بسبب فشل CPCV/PBO/DSR وshadow. لم تُرسل أوامر ولم تُستخدم مفاتيح. التفاصيل في [`SECTION21_IMPLEMENTATION.md`](SECTION21_IMPLEMENTATION.md) و[`section21_report_2026-08-26.json`](section21_report_2026-08-26.json).

القسم 21 لا يخفف حدود المخاطر، ولا يملك سلطة Live مباشرة، وأي تغير هيكلي يحتاج مراجعة. أضيف القسم 22 كحلقة معايرة وذاكرة مناعية review-only؛ الاقتراحات محكومة بنطاقات آمنة، والذاكرة لا تخفف إلا عبر اضمحلال تدريجي واختبار ظلي. تحقق القسم 22 على 1000 شمعة عامة نتج عنه اقتراح واحد، صفر تنفيذ، 44 antigen proxy، و43 كاشفًا محتفظًا، مع رفض بوابات CPCV/PBO/DSR/shadow؛ لا توجد دعوى تحسن. التفاصيل في [`SECTION22_IMPLEMENTATION.md`](SECTION22_IMPLEMENTATION.md) و[`section22_report_2026-08-26.json`](section22_report_2026-08-26.json).

مفاتيح Sandbox وLive، فحص منصات المستخدم، وتشغيل Windows الفعلي ما تزال خارج هذه البيئة.

أضيف فحص جاهزية موحّد (`trading_bot.ops.readiness`) يعرض Paper وSandbox وLive دون طباعة الأسرار، ويعتبر خانة Live اختيارية ومغلقة افتراضيًا. أضيف القسم 24 كطبقة سياق للأحداث والجلسات واللغات؛ لا يحول المشاعر أو الأخبار إلى أوامر ولا يخفف المخاطر. كما أضيف سجل قدرات قائم على الدليل لاستخلاص المفيد من مراجع خارجية دون تكرار المعمارية الحالية.
 كما أضيف فحص مصادر عام لـBinance/Coinbase/Kraken؛ في آخر تشغيل كانت فروق الأسعار ضمن 1% لكن latency القصوى 2518.9168ms تجاوزت حد 500ms، لذلك `signal_allowed=false` ولا يجوز استعمال الناتج كإشارة. التقرير الخام محفوظ في [`cross_source_report_2026-08-26.json`](cross_source_report_2026-08-26.json).

### تحقق القسم 23

شغّل `scripts/orca_section23_real.py` بقراءة فقط من Binance العام. جرى قياس quote latency = 3278.9295 ms وorder-book latency = 2763.9149 ms مقابل حد 500 ms، ففعل النظام Kill-Switch ولم يسمح بأي قرار تنفيذ. بلغ VPIN التشخيصي 0.216484، ولم تُرسل أوامر أو معاملات DeFi، ولم تُستخدم مفاتيح. بقي الحجز القانوني فعالًا لغياب مراجعة قانونية وترخيص خارجي موثق. التفاصيل في [`SECTION23_IMPLEMENTATION.md`](SECTION23_IMPLEMENTATION.md) و[`section23_report_2026-08-26.json`](section23_report_2026-08-26.json).

## مراجع التنفيذ

1. [CCXT Manual](https://github.com/ccxt/ccxt/wiki/manual) — الواجهة الموحدة، sandbox، واشتراط تفعيل sandbox قبل الطلب الأول.
2. [Binance Spot Testnet General Information](https://developers.binance.com/en/docs/products/spot/testnet/general-info) — بيئة الاختبار الرسمية.
3. [Binance Spot Testnet REST API](https://developers.binance.com/en/docs/products/spot/testnet/rest-api) — نقطة API الخاصة بالاختبار.
4. [Coinbase Advanced Trade API Overview](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/overview) — REST وWebSocket وإدارة الأوامر.
