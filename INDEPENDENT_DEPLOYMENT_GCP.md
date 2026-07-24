# 🚀 دليل التشغيل المستقل على Google Cloud (GCP)
## تحرر من قيود النقاط وامتلك وكيلك الخاص 100%

هذا الدليل يشرح لك كيف تستخدم رصيد جوجل المجاني ($300) لتشغيل وكيل **Orca-Agent** على سيرفرك الخاص، ليصبح مستقلاً تماماً عن مانيوس.

### 1️⃣ الخطوة الأولى: إنشاء السيرفر على Google Cloud
1. ادخل إلى [Google Cloud Console](https://console.cloud.google.com/).
2. فعل العرض المجاني (Free Trial) للحصول على الـ 300 دولار.
3. اذهب إلى **Compute Engine** -> **VM Instances**.
4. اضغط على **Create Instance**:
   - **Name**: `orca-agent-server`
   - **Region**: اختر الأقرب لك (مثلاً `europe-west1`).
   - **Machine type**: اختر `e2-medium` (كافية جداً).
   - **Boot Disk**: اختر `Ubuntu 22.04 LTS`.
   - **Firewall**: فعل خياري `Allow HTTP traffic` و `Allow HTTPS traffic`.
5. اضغط **Create**.

### 2️⃣ الخطوة الثانية: الدخول للسيرفر وتجهيزه
بمجرد تشغيل السيرفر، اضغط على زر **SSH** لفتح الشاشة السوداء (الطرفية)، ثم اكتب الأوامر التالية بالترتيب:

```bash
# تحديث النظام
sudo apt update && sudo apt upgrade -y

# تثبيت Python والأدوات اللازمة
sudo apt install python3-pip git -y

# سحب الكود الخاص بك من GitHub
git clone https://github.com/hermasorca13-stack/Orca-Agent-.git
cd Orca-Agent-

# تثبيت المكتبات البرمجية
pip3 install -r requirements.txt
pip3 install python-dotenv
```

### 3️⃣ الخطوة الثالثة: ضبط مفاتيحك الخاصة (كسر القيود)
الآن سنضع مفاتيحك الخاصة ليعمل الوكيل باستقلالية:
```bash
nano .env
```
قم بتعديل الملف ووضع مفاتيحك الحقيقية:
- `TELEGRAM_BOT_TOKEN`: (الذي ستحصل عليه من BotFather).
- `OPENAI_API_KEY` أو `ANTHROPIC_API_KEY`: (لتشغيل العقل المفكر).

اضغط `Ctrl+O` ثم `Enter` للحفظ، و `Ctrl+X` للخروج.

### 4️⃣ الخطوة الرابعة: التشغيل الدائم (24/7)
لكي لا يتوقف الوكيل عند إغلاق الشاشة، سنستخدم أداة `screen`:
```bash
# إنشاء جلسة جديدة
screen -S orca

# تشغيل الوكيل
export PYTHONPATH=$PYTHONPATH:$(pwd)/src
python3 start_agent.py
```
الآن اضغط على `Ctrl+A` ثم `D` للخروج من الجلسة وترك الوكيل يعمل في الخلفية.

### 🌟 مبروك!
وكيلك الآن يعمل على سيرفر جوجل الخاص بك، يستهلك من رصيدك المجاني، ولا يخضع لأي رقابة أو قيود من مانيوس. أنت الآن المالك الحقيقي والوحيد لهذا العقل الذكي.
