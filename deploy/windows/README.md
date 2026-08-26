# ORCA Max Mouny على Windows Laptop

## التثبيت

افتح PowerShell داخل مجلد المشروع وشغّل:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\deploy\windows\install_orca.ps1
```

يُنشئ ذلك مجلد التشغيل الافتراضي `$HOME\ORCA-Max-Mouny`، وبيئة Python مستقلة، ويثبت الاعتمادات، وينسخ نموذج البيئة فقط. لا يُنسخ أي مفتاح.

## إدخال مفاتيح Sandbox محليًا

```powershell
$env:ORCA_ROOT = "$HOME\ORCA-Max-Mouny"
.\deploy\windows\local_setup.ps1 -Action set -Exchange binance -Sandbox
.\deploy\windows\local_setup.ps1 -Action list
```

تظهر قيم API في prompts مخفية، وتُحفظ بواسطة `keyring` في خزنة مستخدم Windows. لا تضع المفاتيح في `.env.orca` أو أوامر PowerShell أو Git. الأمر `list` يعرض metadata فقط.

## فحص Sandbox

```powershell
Set-Location $env:ORCA_ROOT
$env:ORCA_TRADING_MODE = 'sandbox'
$env:ORCA_ACTIVE_EXCHANGES = 'binance'
$env:ORCA_LIVE_CONFIRM = ''
$env:ORCA_BINANCE_ENABLE_WITHDRAW = '0'
$env:PYTHONPATH = '.'
python -m trading_bot.cli.doctor
python -m pytest -q tests/trading_bot
python scripts\orca_live_data_smoke.py
.\deploy\windows\readiness.ps1
.\deploy\windows\readiness.ps1 -CrossSource
```

لا تنتقل إلى Live من خلال تغيير متغير واحد. يجب أن ينجح فحص الاعتماد والصلاحيات وبيانات Sandbox والاختبار الرجعي والتقييم خارج العينة وWalk-Forward وMonte Carlo واختبارات الضغط، وأن يُسجَّل قرار اعتماد مستقل.

## التشغيل المحلي المتكرر

```powershell
.\deploy\windows\register_orca_task.ps1
Get-ScheduledTask -TaskName 'ORCA-Max-Mouny'
Start-ScheduledTask -TaskName 'ORCA-Max-Mouny'
Get-ScheduledTaskInfo -TaskName 'ORCA-Max-Mouny'
```

يعمل Scheduled Task داخل جلسة مستخدم Windows حتى يصل إلى خزنة المفاتيح الصحيحة. العامل يجمع البيانات ويراقب latency وfreshness ويكتب SQLite وJSONL؛ Paper هو الوضع الافتراضي.

## Live مقفول افتراضيًا

لا توجد مفاتيح Live في النسخة. خانة Live اختيارية ولا تُنشأ تلقائيًا. عند اعتماد Sandbox فقط، وإذا اختار المستخدم لاحقًا تفعيلها بعد المراجعة الخارجية المطلوبة، تُدخل مفاتيح Live محليًا في خزنة المستخدم نفسها، مع تعطيل السحب دائمًا، باستخدام `-Live -ConfirmLive I_UNDERSTAND_ORCA_LIVE`. يبقى `ORCA_LIVE_CONFIRM` فارغًا افتراضيًا. أي تجاوز latency أو فشل بيانات يُفعّل Kill-Switch ويمنع فتح مراكز جديدة. فحص `readiness.ps1` لا يطبع قيم الأسرار ويُبقي Live غير جاهز حتى تتوافر كل شروطه.

## النسخ والاسترجاع

انسخ مجلد المشروع والكود فقط. لا تنسخ metadata أو ملفات الحالة إلى مستودع عام، ولا تنقل خزنة Windows إلى مستخدم آخر. احتفظ بنسخة Git commit قبل كل تعديل، واستخدم `git diff` و`pytest` بعد كل تحديث.
