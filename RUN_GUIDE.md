# 🐋 Orca Agent — التشغيل الحقيقي

دليل تشغيلي من الصفر. كل الأوامر هنا **مجرّبة** على هذا الـ repo.

---

## 0. المتطلبات
- Python 3.11+
- حساب GitHub عليه token فيه scope: `repo`, `workflow`
- Telegram Bot Token من @BotFather

## 1. الإعداد
```bash
git clone https://github.com/hermasorca13-stack/Orca-Agent-Unified.git
cd Orca-Agent-Unified
pip install -r requirements.txt
cp .env.example .env
# عدّل .env بالـ tokens الحقيقية
```

## 2. التحقق قبل التشغيل
```bash
python3 scripts/smoke_test.py     # Telegram + GitHub live check
python3 orca.py doctor            # engineering checks
python3 orca.py status            # system status
```

## 3. التشغيل
### A) محلي (development)
```bash
python3 orca.py bot
# افتح Telegram وجرب: /start /status /skills /brain /agent
```

### B) Docker (production)
```bash
docker compose up -d --build
docker compose logs -f orca-bot
```

## 4. أوامر Telegram
| Command | الوظيفة |
|---------|---------|
| `/start` | رسالة ترحيب + قائمة الأوامر |
| `/status` | حالة النظام (Telegram + GitHub + tokens) |
| `/skills` | قائمة الـ 30+ skill |
| `/brain` | حالة الـ LLM bridge |
| `/agent <prompt>` | إرسال prompt للـ LLM |
| `/sync` | رفع التغييرات لـ GitHub |
| `/device` | معلومات جهاز Android |
| `/exec <cmd>` | تنفيذ shell command |
| `/token` | توليد API token جديد |
| `/tap <x> <y>` | tap على Android |
| `/swipe x1 y1 x2 y2 [ms]` | swipe |
| `/text <msg>` | كتابة نص |
| `/verify` | engineering verify |

## 5. تفعيل الـ LLM (اختياري لكن مهم)
عدّل `.env`:
```bash
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
# أو
OPENAI_API_KEY=sk-...
```
ثم:
```bash
python3 orca.py doctor    # لازم يطلع: reason=llm
```

## 6. CI/CD
- `.github/workflows/ci.yml` — pytest + ruff + doctor على كل push
- `.github/dependabot.yml` — weekly updates للـ pip + github-actions

## 7. البنية
```
orca-agent/
├── orca.py                    # entrypoint الوحيد (bot|sync|status|tokens|doctor)
├── core/                      # canonical engine (config, agent, memory, skills)
├── src/                       # domain kernels (re-exports من core)
├── telegram_bot/              # long-polling bot
├── github_sync/               # Contents API push
├── api_manager/               # token system (singleton)
├── android_bridge/            # ADB + Termux
├── skills/                    # skills registry
├── tests/                     # unit tests
├── scripts/                   # smoke_test.py + bot_doctor.sh
├── data/                      # SQLite memory
├── logs/                      # rotating logs
└── .github/workflows/         # CI
```

## 8. حل المشاكل
- **"Conflict: terminated by other getUpdates"** → في instance تاني شغال. `pkill -f orca.py` ثم أعد.
- **"Bad credentials"** من GitHub → token منتهي. ولّد واحد جديد من https://github.com/settings/tokens
- **LLM ما بيشتغل** → تأكد إن `LLM_API_KEY` مش فاضي في `.env` ثم `python3 orca.py doctor`
