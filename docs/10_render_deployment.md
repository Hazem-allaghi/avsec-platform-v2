# نشر على Render.com — دليل خطوة بخطوة (من المتصفح، يعمل من الهاتف)

## المتطلبات قبل البدء
- ✅ Migration منفَّذ (`0001_init.sql`) — تم.
- ✅ Seed Part 1 + Part 2 منفَّذان — تم، تحقق منه.
- ⏳ **Connection string لـ Postgres** (من Project Settings → Database →
  Connection string → URI) — بانتظارك.
- حساب مجاني على render.com (يمكن التسجيل بحساب GitHub مباشرة).

## الخطوات

### 1) رفع الكود إلى GitHub
Render يحتاج مستودع Git ليبني منه. إن لم يكن لديك مستودع بعد:
- أنشئ مستودعًا جديدًا فارغًا على GitHub (من المتصفح، بلا حاجة لسطر أوامر).
- ارفع محتوى مجلد `avsec-platform/` الذي أرسلته لك بالكامل (يمكن السحب
  والإفلات لملف ZIP عبر واجهة GitHub الوِيب على "Add file → Upload files").

### 2) إنشاء Web Service جديد على Render
- Render Dashboard → **New → Web Service** → اختر مستودعك.
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** (Render يقرأ `Procfile` تلقائيًا، لا حاجة لإدخال شيء —
  لكن إن طُلب منك، أدخل بالضبط ما في `Procfile`)
- **Instance Type:** Free يكفي للاختبار الأولي.

### 3) متغيرات البيئة (Environment Variables) — الأهم
من تبويب **Environment** في إعدادات الخدمة، أضف:

| المفتاح | القيمة |
|---|---|
| `AVSEC_DB_BACKEND` | `postgres` |
| `DATABASE_URL` | Connection string الكامل من Supabase (`postgresql://postgres:...`) |
| `SUPABASE_JWT_SECRET` | Legacy JWT secret الذي أرسلته سابقًا |
| `SUPABASE_JWT_AUD` | `authenticated` (القيمة الافتراضية أصلًا، لا حاجة لتغييرها إلا إذا اختلفت) |
| `AVSEC_DEBUG` | اتركه فارغًا أو `0` (لا تُفعّل Debug في الإنتاج) |

### 4) Deploy
اضغط **Create Web Service** — Render يبني وينشر تلقائيًا. بعد انتهاء البناء
(2-5 دقائق عادة)، يظهر لك رابط بصيغة:
`https://avsec-platform-xxxx.onrender.com`

هذا هو **Preview URL** الفعلي. افتحه مباشرة من الهاتف → يجب أن تظهر لوحة
المشرف (Supervisor Dashboard) متصلة بقاعدة بياناتك الحقيقية على Supabase.

### 5) التحقق السريع بعد النشر
افتح `https://<رابطك>/health` — يجب أن يعطي `{"status":"ok"}`. إذا فشل الاتصال
بقاعدة البيانات، ستظهر رسالة خطأ من psycopg2 في **Logs** بتبويب الخدمة على
Render — أرسل لي نص الخطأ كاملاً إن حدث، لأصلحه (هذا أول اختبار حقيقي لهذا
المسار، راجع الملاحظة أدناه).

## ⚠️ ملاحظة أمانة متكررة عمدًا
مسار Postgres (`db_postgres` wrapper داخل `db.py`) **لم يُختبَر فعليًا ضد
قاعدة Postgres حقيقية بعد** — لا psycopg2 مثبّتة في بيئتي، ولا اتصال شبكة.
كُتب بعناية ومطابقًا لأنماط الاستعلامات المُثبَتة فعليًا ضد SQLite طوال هذا
المشروع، لكن **أول اختبار حقيقي له سيكون عند نشرك هذا فعليًا على Render**. من
المتوقع (لا المؤكد) أن يعمل من أول مرة، لكن إن ظهر أي خطأ في الـ Logs، هو
غالبًا أحد اثنين معروفين مسبقًا وسهلا الإصلاح:
1. تحويل نوع بيانات (مثال: نص عادي إلى `uuid` أو `jsonb`) يحتاج `::type` صريح
   في مكان ما.
2. اختلاف طفيف في اسم عمود بين `db/schema.sql` (SQLite) و
   `supabase/migrations/0001_init.sql` (Postgres) لم يُكتشف من قبل لأنه لم
   يُختبَر تشغيليًا.

أرسل نص أي خطأ كما هو، وسأصلحه مباشرة.
