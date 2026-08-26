# Live Public Data Verification

## 2026-08-26 UTC

تم تشغيل `scripts/orca_live_data_smoke.py` من داخل المستودع، ونجح جلب بيانات عامة حقيقية من Binance عبر REST لزوج `BTC/USDT`.

| الحقل | القيمة المقاسة |
|---|---:|
| المصدر | Binance public REST |
| الزوج | BTC/USDT |
| bid | 79125.85 |
| ask | 79125.86 |
| spread | 0.0012638 bps |
| حجم 24 ساعة | 1,691,672,793.210517 USD |

كما نجح `scripts/orca_market_sources_smoke.py` في جلب دفتر أوامر حقيقي من Binance، و10 شموع دقيقة، وبيانات Futures للتمويل والفائدة المفتوحة دون إرسال أي أمر:

| المصدر | النتيجة |
|---|---|
| Spot order book | 5 مستويات bid و5 مستويات ask |
| Spot OHLCV | 10 شموع 1m |
| Futures funding | `0.00006149` |
| Futures open interest | `106042.681` |
| أعلى latency مقاسة | `2875.67ms` |

شغّل العامل الدائم مرة واحدة أيضًا، فسجّل اللقطة وفعّل Kill-Switch بسبب تجاوز latency حد `500ms`. هذا السلوك يطابق بوابة السلامة: البيانات وصلت فعلًا، لكن لا يسمح النظام بالمتابعة التنفيذية عند هذا التأخر.

كما نجح `scripts/orca_context_smoke.py` في جلب مؤشر Fear & Greed وقيمة BTC بالنسبة لمتوسط 200 أسبوع من مصادر عامة:

| الحقل | القيمة |
|---|---:|
| Fear & Greed | 65 |
| BTC فوق متوسط 200 أسبوع | نعم |

هذه نتيجة تحقق من **مصدر عام** وليست إثباتًا لاتصال حساب تداول خاص أو تنفيذ أمر حقيقي. زمن الاستجابة يظل مدخلًا لبوابة المخاطر، وتبقى حدود البيانات والمصادر الخارجية الأخرى بحاجة إلى تشغيل مستمر على مضيف دائم.

المصادر البرمجية المستخدمة:

- Binance public REST: `https://api.binance.com/api/v3/ticker/bookTicker`
- Binance public REST: `https://api.binance.com/api/v3/ticker/24hr`
- Binance public REST: `https://api.binance.com/api/v3/klines`
- Alternative.me Fear & Greed: `https://api.alternative.me/fng/?limit=1`
