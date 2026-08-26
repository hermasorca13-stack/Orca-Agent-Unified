# نشر ORCA Max Mouny على جهاز مستقبلي

## تجهيز النظام

يحتاج التشغيل الدائم إلى Linux أو WSL، Python 3.11 أو أحدث، اتصال ثابت، مساحة تخزين دائمة، ومستخدم خدمة مستقل باسم `orca`. مواصفة الموارد العالية المذكورة في المسار هي 16 نواة و64GB RAM؛ لا يتم افتراض توفرها في بيئة العمل الحالية.

## تثبيت المشروع

```bash
git clone https://github.com/hermasorca13-stack/Orca-Agent-Unified.git /opt/orca-agent-unified
cd /opt/orca-agent-unified
sudo bash deploy/install_orca_service.sh
```

قبل تشغيل الخدمة، أنشئ `/etc/orca/orca.env` بصلاحيات `0640` ومجموعة `orca`. ابدأ دائمًا بـ:

```env
ORCA_TRADING_MODE=paper
ORCA_ACTIVE_EXCHANGES=
ORCA_LIVE_CONFIRM=
```

بعد تثبيت موصلات الاختبار ومفاتيح sandbox، يمكن استخدام `sandbox`، ويجب إنشاء مفاتيح sandbox من شبكة الاختبار نفسها. لا تُنسخ مفاتيح الإنتاج إلى sandbox.

لا يُفتح وضع `live` إلا بعد اكتمال اختبارات Paper وsandbox، وفحص الصلاحيات في كل منصة، والتأكد من أن صلاحية السحب غير مفعلة. يتطلب الوضع الحقيقي قيمة البيئة:

```env
ORCA_TRADING_MODE=live
ORCA_LIVE_CONFIRM=I_UNDERSTAND_ORCA_LIVE
ORCA_ACTIVE_EXCHANGES=binance
ORCA_BINANCE_SANDBOX=0
ORCA_BINANCE_ENABLE_WITHDRAW=0
```

ثم يُعاد تشغيل الخدمة ويُفحص السجل. ملف الخدمة الحالي يشغل عامل مراقبة وجمع بيانات دائمًا في وضع Paper الافتراضي؛ يسجل اللقطات في SQLite ويراقب freshness وlatency ويطلق Kill-Switch عند الفشل. ربط دورة الإشارات والتنفيذ الحية يجب أن يتم بعد اعتماد بيانات السوق والاختبارات التشغيلية على الجهاز المضيف، وليس بإخفاء ذلك خلف عامل حالة.

## فحوص ما بعد النشر

```bash
sudo systemctl status orca-max-mouny
journalctl -u orca-max-mouny -f
cd /opt/orca-agent-unified
PYTHONPATH=. python3 -m trading_bot.cli.doctor
PYTHONPATH=. pytest -q tests/trading_bot
```

يجب الاحتفاظ بملف البيئة خارج Git، ومراجعة `data/orca_max_mouny/audit.jsonl` و`kill.json` وملف SQLite قبل أي انتقال بين الأوضاع.
