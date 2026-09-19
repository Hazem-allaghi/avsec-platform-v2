# Aviation Security Platform — Architecture (v0.1)

## 1. مبدأ التصميم
النظام V1 مخصص لشركة طيران واحدة (Afriqiyah Airways — AAW) لكن كل مكوّن مصمم
ليكون **Tenant-aware من اليوم الأول**، بحيث لا يحتاج المشروع إعادة هيكلة لدعم
شركات متعددة لاحقًا — فقط تفعيل عزل بيانات إضافي.

المصدر التشغيلي الأساسي لكل Workflow/Checklist/Rule هو:
`AAW_Security_Manual_final_2021_2_.pdf` (Rev 01, 01.10.2021) — يُشار إليه في كل
الوثائق بالرمز **[AAWSM §x.x.x]**.
أي عمل سابق (AVSEC-OMS / AeroSecure) يُعتبر **مرجعًا تصميميًا فقط**، ويُستبدل أي
جزء منه يخالف الدليل الرسمي.

## 2. الطبقات المعمارية

```
┌──────────────────────────────────────────────────────────────┐
│  Clients                                                       │
│  - Mobile/Web App (Ramp/Security Officer) — Offline-first PWA  │
│  - Supervisor Dashboard (Web)                                  │
│  - Admin Console (Manual/Workflow versioning per airline)      │
└───────────────┬──────────────────────────────────────────────┘
                 │ HTTPS/JSON (+ Offline Sync Queue)
┌───────────────▼──────────────────────────────────────────────┐
│  API Layer (Backend)                                           │
│  - Auth & RBAC                                                 │
│  - Workflow Engine (state machine per flight)                  │
│  - Rules Engine (Blocking Conditions → Clearance decision)     │
│  - Checklist Service                                           │
│  - Audit Trail Service (append-only, WORM-style)                │
│  - Sync Service (conflict resolution: last-writer + device log)│
└───────────────┬──────────────────────────────────────────────┘
                 │
┌───────────────▼──────────────────────────────────────────────┐
│  Data Layer                                                     │
│  - tenants / airlines                                          │
│  - manual_versions (per-airline, versioned procedures)         │
│  - flights, workflow_stages, checklist_instances               │
│  - security_events, incidents                                  │
│  - audit_log (immutable)                                       │
│  - gps_pings, sync_log                                          │
└──────────────────────────────────────────────────────────────┘
```

## 3. Multi-Tenancy Model — ✅ قرار محسوم (Waled، 08_open_decisions.md #1)

**القرار النهائي لـ V1/V2:** **Single-Tenant** بتصميم Modular نظيف. لا تُنفَّذ
RLS متعددة المستأجرين الآن. السبب: الاندماجات (كشائعات دمج AAW/LCAA) تستغرق
سنوات؛ إضافة Multi-tenancy الكاملة مبكرًا تُعقّد سياسات RLS والأداء دون داعٍ
تشغيلي حالي.

**ما يبقى ثابتًا رغم ذلك (عزل نظيف، لا تقنية متعددة المستأجرين):**

| مستوى | القرار الفعلي |
|---|---|
| `airline_id` | عمود أساسي في كل جدول حساس (كان مصممًا هكذا أصلًا) — **يُبقي الترحيل لاحقًا عبر DDL بسيطًا إن استدعت الحاجة فعليًا**، لكن لا RLS متعددة المستأجرين تُبنى الآن |
| `manual_version_id` | نسخة واحدة نشطة (AAWSM Rev01-2021) |
| Workflow Templates | Template واحد مشتق من AAWSM، بلا آلية استنساخ متعددة الشركات في هذا الـ Sprint |
| Core Platform | كود مشترك، لكن بلا طبقة Tenant Isolation إضافية (RLS بحسب `airline_id`) — تُضاف **فقط** إذا تأكد قرار الدمج/التوسع فعليًا مستقبلًا |

**القرار المعماري:** لا "Hardcoding" لأي منطق خاص بـ AAW داخل الكود (هذا
مبدأ ثابت بغض النظر عن قرار Multi-tenancy) — كل قاعدة عمل تبقى بيانات في
`security_rules`. لكن **لا تُبنى بنية عزل RLS متعددة المستأجرين في هذا
الإصدار** — قرار مقصود لتفادي التعقيد قبل الحاجة الفعلية.

## 4. Technology Stack (V1 — MVP قابل للتشغيل فورًا في هذه البيئة)

- **Backend:** Python 3.12 + Flask (متوفر فعليًا في البيئة، بدون الحاجة لتثبيت
  حزم عبر الإنترنت) + `sqlite3` (stdlib) — قابل للترقية لاحقًا إلى
  PostgreSQL/FastAPI في بيئة إنتاج حقيقية دون تغيير منطق الأعمال (SQL مكتوب
  بشكل متوافق مع Postgres قدر الإمكان).
- **DB (Local MVP/Demo):** SQLite للـ MVP المحلي القابل للاختبار الآن → مخطط
  (`schema.sql`) مصمم للترحيل المباشر إلى PostgreSQL (نفس الأسماء/العلاقات).
- **DB + Auth (المسار الحقيقي — قرار #5):** **Supabase (Postgres + Auth +
  RLS)** — انظر `supabase/migrations/` و`docs/09_supabase_integration.md`.
  هذا هو المسار المعتمد للإنتاج؛ SQLite يبقى فقط لتطوير/عرض محلي سريع بلا
  اتصال شبكة.
- **Frontend (MVP):** صفحة Dashboard وواجهة ضابط أمن كـ HTML/JS بسيط يستهلك
  الـ API — إثبات مفهوم قابل للاختبار الآن، وليس Prototype شكلي منفصل عن
  Backend كما كان في AVSEC-OMS السابق.
- **Offline Sync:** طابور محلي (IndexedDB على العميل — مُخطط، غير مُنفّذ في
  هذا الـ Sprint، محطة تالية مباشرة بعد Auth حسب قرار #7) + `sync_log` على
  الخادم لتتبّع أصل كل تحديث ومطابقته.
- **GPS:** حقل `lat/lng/accuracy/captured_at` يُرفق بكل حدث تفتيش حرج (تفتيش
  طائرة، تسليم كاترينج) — [AAWSM §2 AVSEC-OMS legacy design, يُطابق مبدأ
  BaggageSecurity.GPSLocation الوارد سابقًا].

## 5. حدود هذا الـ Sprint (ما تم بناؤه فعليًا الآن)
- ✅ Schema كامل قابل للتشغيل (SQLite) + قابل للترحيل.
- ✅ Rules Engine حقيقي (يقرأ القواعد من DB، لا كود مكتوب يدويًا).
- ✅ Workflow Engine بحالات محددة (state machine) تفرض الترتيب.
- ✅ Audit Trail تلقائي على كل Mutation.
- ✅ API عامل فعليًا (Flask) قابل للاختبار عبر curl/pytest.
- ✅ Dashboard بسيط يعرض حالة الرحلات و Blocking Reasons.
- ⏳ Offline Sync (IndexedDB client) — مصمم لكن غير مُنفّذ (يحتاج بيئة موبايل/PWA
  فعلية).
- ⏳ Multi-airline Admin Console (رفع دليل جديد وتوليد Workflow منه تلقائيًا) —
  مصمم بنيويًا (جدول `manual_versions` + `security_rules` قابل للتعبئة) لكن
  واجهة الرفع نفسها غير مبنية في هذا الـ Sprint.
- ⏳ Push Notifications / Real-time (WebSocket) — غير مُنفّذ.

انظر `docs/08_open_decisions.md` لكل قرار يحتاج توقيعك قبل الاعتماد.
