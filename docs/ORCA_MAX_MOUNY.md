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
| `assets/orca_max_mouny/orca-whale.svg` | شعار حوت الأوركا بصيغة SVG |
| `deploy/` | قالب Docker/systemd ونشر مستقل للمضيف الدائم |

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
python3 -m trading_bot.cli.doctor
pytest -q tests/trading_bot
```

لتشغيل sandbox، أنشئ مفاتيح من شبكة الاختبار في المنصة نفسها، ثم اضبط `ORCA_TRADING_MODE=sandbox` و`ORCA_ACTIVE_EXCHANGES=binance` واملأ متغيرات Binance من خارج Git. لا تُستخدم مفاتيح الإنتاج في sandbox، ولا تُفعّل `ORCA_*_ENABLE_WITHDRAW`.

لتفعيل live، يجب أولًا إجراء مراجعة مستقلة للإعدادات والاعتماد والحدود، ثم ضبط `ORCA_TRADING_MODE=live` و`ORCA_ACTIVE_EXCHANGES` وإدخال الاعتمادات في مدير أسرار أو متغيرات بيئة خارج المستودع. البرنامج لا ينفّذ صفقة من تلقاء نفسه عند الإقلاع؛ يبدأ التشغيل من خلال دورة الإشارة والتنفيذ التي يجب ربطها بمصدر بيانات حقيقي بعد اختبار sandbox.

## تسلسل التشغيل الموحّد

يبدأ النظام بتحميل الإعدادات والتحقق من حدود المخاطر، ثم ينشئ موصلات السوق ويجمع الأسعار، ويحسب المؤشرات والفروق والتمويل والسيولة، ويجري الاختبارات الإحصائية اللازمة، ثم يمرر الإشارة إلى بوابة التكاليف والمخاطر. عند الموافقة، يحدد الحجم عكسيًا مع التقلب، وينفذ الدخول على شرائح صغيرة، ويعيد حساب الحياد والتعرض، ثم يدير الخروج المرحلي والتوقف الطارئ ويكتب كل مرحلة في سجل UTC.

## فحوص القبول

قبل أي انتقال من Paper إلى sandbox يجب أن ينجح اختبار رجعي لا يقل عن 200 صفقة تاريخية، واختبار خارج العينة، واختبار Walk-Forward، واختبار Monte Carlo، واختبارات انهيار السعر واتساع السبريد وتوقف المنصة وفشل API وارتفاع التمويل وفشل التحوط. يجب تسجيل النتائج قبل الرسوم وبعد الرسوم والتمويل والانزلاق والتكاليف الأخرى، وقياس Sharpe وProfit Factor وMax Drawdown وWin Rate وSortino وCalmar.

معايير القبول المستهدفة من وثيقة المتطلبات هي Sharpe أكبر من 2.0، وProfit Factor أكبر من 2.0، وMax Drawdown أقل من 20%، وWin Rate أكبر من 50%، مع اعتماد السجل الكامل وجميع الحسابات والإيداعات والسحوبات والرسوم والتمويل والانزلاق والتصفية عند احتساب الأداء.

## مراجع التنفيذ

1. [CCXT Manual](https://github.com/ccxt/ccxt/wiki/manual) — الواجهة الموحدة، sandbox، واشتراط تفعيل sandbox قبل الطلب الأول.
2. [Binance Spot Testnet General Information](https://developers.binance.com/en/docs/products/spot/testnet/general-info) — بيئة الاختبار الرسمية.
3. [Binance Spot Testnet REST API](https://developers.binance.com/en/docs/products/spot/testnet/rest-api) — نقطة API الخاصة بالاختبار.
4. [Coinbase Advanced Trade API Overview](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/overview) — REST وWebSocket وإدارة الأوامر.
