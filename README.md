# 🏭 Reactor Factory Bot

بوت تليجرام لإنشاء بوتات ريأكشن فرعية، مع نظام **اشتراك إجباري** و **إذاعة عامة** للمطور فقط.

---

## ✨ المميزات

- 🎞️ رسالة `/start` بـ GIF + كل التعامل بأزرار Inline
- 🔒 اشتراك إجباري متعدد القنوات (يدار من البوت بأزرار)
- 📢 إذاعة من المطور لـ:
  - كل مستخدمي المصنع
  - كل القنوات المتصلة بالبوتات الفرعية
- 🤖 إنشاء بوتات ريأكشن فرعية بتوكن من المستخدم
- ✅ موافقة المطور على كل بوت قبل التفعيل
- 🎨 أزرار ملوّنة بالإيموجي (🟢 ✅ ❌ 🔙) للتمييز البصري

> **ملاحظة عن لون الأزرار:** Telegram Bot API لا يدعم تغيير لون أزرار Inline Keyboard برمجياً — اللون يتبع ثيم المستخدم. الإيموجي هو الحل العملي الوحيد للتمييز.

---

## 🚀 النشر على Railway (موصى به)

### 1) ارفع الكود على GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/USERNAME/REPO.git
git push -u origin main
```
> ⚠️ تأكد إن `.gitignore` بيستبعد `.env` و `data/`

### 2) في Railway Dashboard
1. **New Project** → **Deploy from GitHub repo** → اختر الريبو
2. روح **Variables** وضيف:
   ```
   BOT_TOKEN=توكن_البوت_من_BotFather
   DEVELOPER_ID=ايدي_تليجرام_بتاعك
   DATA_DIR=/data
   ```
3. روح **Settings** → **Volumes** → **New Volume**:
   - Mount path: `/data`
   - ده بيحمي ملفات JSON من الحذف مع كل deploy ✅

4. الـ deploy هيشتغل أوتوماتيك. لو مشتغلش، اضغط **Deploy**.

### 3) تأكد إنه شغال
- روح **Deployments** → **View Logs**
- المفروض تشوف: `🏭 المصنع شغّال…`
- ابعت `/start` للبوت في تليجرام

---

## 💻 التشغيل المحلي

```bash
# 1) ثبّت المتطلبات
pip install -r requirements.txt

# 2) انسخ ملف البيئة وعدّله
cp .env.example .env
# افتح .env وحط BOT_TOKEN و DEVELOPER_ID

# 3) شغّل
python factory.py
```

---

## 📁 هيكل المشروع

```
reactor_factory/
├── factory.py          # البوت الرئيسي + handlers
├── reactor_bot.py      # كلاس البوت الفرعي
├── reactions.py        # منطق الريأكشن
├── keyboards.py        # كل الأزرار Inline
├── storage.py          # إدارة JSON (users, tokens, channels, force_sub)
├── config.py           # قراءة env variables
├── requirements.txt    # aiogram, aiohttp, dotenv
├── Procfile            # أمر تشغيل Railway
├── railway.json        # إعدادات Railway
├── nixpacks.toml       # إعدادات البناء
├── runtime.txt         # نسخة Python
├── .env.example        # نموذج متغيرات البيئة
└── .gitignore          # استبعاد .env و data/
```

---

## 🔧 لوحة المطور

ابعت `/admin` (للمطور فقط) → هتلاقي:
- 📢 **إذاعة**: ابعت أي رسالة وهتتنشر لكل المستخدمين والقنوات
- 🔒 **قنوات الاشتراك الإجباري**: ضيف/شيل بأزرار
- 📊 **إحصائيات**: عدد المستخدمين، البوتات، القنوات
- ✅ **موافقات**: قبول/رفض البوتات الفرعية

---

## 🛠️ Troubleshooting

| المشكلة | الحل |
|---------|------|
| البوت مش بيرد | تأكد من `BOT_TOKEN` صح في Variables |
| البيانات بتتمسح مع كل deploy | اربط Volume على `/data` وحط `DATA_DIR=/data` |
| `/admin` مش بيشتغل | راجع `DEVELOPER_ID` (لازم رقم بدون اقتباسات) |
| البوت الفرعي مش بيتفعل | المطور لازم يوافق من قائمة "الموافقات المعلقة" |

---

## 📝 رخصة

استخدام شخصي.
