# Aviation Security Platform — MVP (Sprint 1)

**الحالة:** MVP يعمل فعليًا، مُختبَر End-to-End (انظر `tests/e2e_smoke_test.py`
— كل التأكيدات نجحت، شاملة سيناريو حظر → تصحيح → ترخيص، وسيناريو طوارئ كامل).

## التشغيل السريع
```bash
# 1) بناء قاعدة البيانات
python3 -c "
import sqlite3
conn = sqlite3.connect('db/avsec.db')
conn.executescript(open('db/schema.sql').read())
conn.executescript(open('db/seed_data.sql').read())
conn.commit(); conn.close()"

# 2) تشغيل الخادم
python3 -m backend.app.main
# API + Dashboard على http://127.0.0.1:5055  (افتح المتصفح مباشرة على الجذر /)

# 3) (اختياري) تشغيل الاختبار الشامل من نافذة طرفية أخرى
python3 tests/e2e_smoke_test.py
```

## خريطة الوثائق (اقرأ بهذا الترتيب)
| # | الملف | المحتوى |
|---|------|---------|
| 1 | `docs/01_architecture.md` | القرار المعماري، Multi-tenant Model |
| 2 | `docs/02_requirements_matrix.md` | 20 متطلبًا مستخرجًا من AAWSM بمصادرها |
| 3 | `docs/03_master_workflow.md` | تسلسل المراحل من الرحلة حتى Clearance |
| 4 | `docs/04_checklists.md` | CL-01 إلى CL-06 (PASS/FAIL) |
| 5 | `docs/05_roles_permissions.md` | مصفوفة الأدوار والصلاحيات |
| 6 | `docs/06_security_rules.md` | BR-01 إلى BR-10 (Blocking Conditions) |
| 7 | `docs/07_research_log.md` | نتائج التحقق الخارجي (ICAO/LCAA) بمصادرها |
| 8 | **`docs/08_open_decisions.md`** | **⚠️ اقرأ هذا أولًا فعليًا — يحتوي قرارًا يمسّ صميم المشروع** |

## ما تم بناؤه فعليًا (ليس تخطيطًا)
- ✅ `db/schema.sql` + `db/seed_data.sql` — 20 جدولًا، يعمل فعليًا (SQLite الآن،
  متوافق Postgres لاحقًا)، Multi-tenant من اليوم الأول (`airline_id` +
  `manual_version_id` في كل مكان حساس).
- ✅ `backend/app/workflow.py` — Workflow Engine حقيقي بحالات ومنع تخطي مراحل.
- ✅ `backend/app/rules/engine.py` — Rules Engine **يقرأ القواعد من قاعدة
  البيانات** (BR-01..BR-10)، وليس كودًا مكتوبًا يدويًا لكل حالة — أي دليل أمن
  جديد لشركة أخرى يُعرِّف قواعده كبيانات دون لمس هذا الملف.
- ✅ `backend/app/audit.py` — كل Mutation يُسجَّل تلقائيًا (append-only).
- ✅ `backend/app/main.py` — API كامل (Flask) بـ 20+ Endpoint.
- ✅ `frontend/dashboard.html` — لوحة مشرف تعمل فعليًا (تُقدَّم من نفس الخادم
  على `/`)، تعرض حالة كل رحلة، أسباب الحظر الحية، وفتح/إغلاق حالات الطوارئ.
- ✅ `tests/e2e_smoke_test.py` — اختبار كامل يغطي: إنشاء رحلة → حظر مبكر →
  فحص طائرة → مطابقة أمتعة (مع mismatch ثم تصحيحه) → كاترينج (ختم مكسور ثم
  فحص يدوي) → شحن → أختام طائرة → **ترخيص أمني ناجح** → سيناريو طوارئ كامل
  (فتح/حظر/إغلاق) → تدقيق Audit Trail.

## ما لم يُنفَّذ بعد (مُعلَن بوضوح، لا ادّعاء اكتمال)
- ❌ Authentication حقيقي (JWT/Session) — الـ API حاليًا **بلا حماية دخول**
  (user_id يُرسَل كنص عادي في الطلب). **غير آمن للإنتاج إطلاقًا بهذا الشكل.**
- ❌ Offline Sync الفعلي على العميل (IndexedDB + Service Worker) — الجدول
  `sync_log` جاهز في DB لكن لا عميل موبايل/PWA يستخدمه بعد.
- ❌ رفع دليل أمن جديد عبر واجهة (Admin Console) — البنية جاهزة
  (`manual_versions`, `security_rules` قابلة للتعبئة) لكن لا شاشة رفع/تحويل
  تلقائي من PDF إلى قواعد.
- ❌ WebSocket/Push للتحديث اللحظي — اللوحة الحالية Polling كل 15 ثانية فقط.
- ❌ صلاحيات API مُطبَّقة بالكامل حسب `05_roles_permissions.md` — التطبيق
  الحالي يتحقق من الدور في نقاط حرجة فقط (إغلاق حادثة/طوارئ، Override)، وليس
  في كل Endpoint.

## القرار الأهم المطلوب منك الآن
اقرأ **`docs/08_open_decisions.md` — القرار #1**: ظهر أثناء التحقق الخارجي
(بحث عرضي، ليس هدف السؤال) ما يشير إلى خطة دمج AAW مع الخطوط الليبية في ناقل
وطني موحد. هذا لا يوقف العمل الحالي، لكنه **قد يغيّر الأولوية المعمارية
لمرحلة V2 القادمة بشكل جوهري**. لن أتابع بافتراض أي سيناريو دون تأكيدك.
