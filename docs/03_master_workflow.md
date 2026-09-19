# Master Security Workflow — من وصول/تحضير الرحلة حتى Security Clearance

مبني على R-001 وتسلسل الفصول 4–11 و15 في AAWSM. كل مرحلة = صف في
`workflow_stages` بحالة (`PENDING / IN_PROGRESS / PASSED / FAILED / BLOCKED`).

```
[1] FLIGHT_CREATED
     │  (رقم الرحلة، نوع الطائرة، بوابة، threat_level الحالي)
     ▼
[2] AIRCRAFT_SECURITY_CHECK          [AAWSM §8.0-8.2]
     │  Checklist ديناميكي حسب aircraft_type
     │  توقيعات: Flight Deck + Cabin Crew + Station Engineer
     │  FAIL/Suspect Item → حالة EMERGENCY منفصلة (لا تُكمل التسلسل)
     ▼
[3] PASSENGER_SCREENING_BAGGAGE_RECONCILIATION   [AAWSM Ch.4-5-7]
     │  - فحص أمتعة اليد + الركاب (نسب تختلف حسب threat_level)
     │  - فحص 100% الأمتعة المسجَّلة
     │  - مطابقة راكب↔حقيبة (لا حقيبة بلا راكب حاضر على متن الطائرة)
     ▼
[4] CATERING_SECURITY                [AAWSM §9]
     │  - تحقق الأختام (truck seal + cart seal)
     │  - أي seal broken → فحص يدوي كامل إلزامي قبل المتابعة
     ▼
[5] CARGO_MAIL_SECURITY (إن وجد شحن على هذه الرحلة)  [AAWSM Ch.11]
     │  - تصنيف Known/Regulated/Unknown
     │  - Unknown → فحص إلزامي قبل القبول
     ▼
[6] SEAL_VERIFICATION (أختام الطائرة نفسها - Night-stop/Transit)  [Appendix I]
     │  - رقم الختم + الحالة، أي broken/missing → حادثة أمنية إلزامية
     ▼
[7] SECURITY_INCIDENT_REVIEW         [AAWSM Ch.15]
     │  - مراجعة: هل توجد حوادث مفتوحة (open) مرتبطة بهذه الرحلة؟
     │  - حادثة مفتوحة بخطورة Major/Critical → تمنع الانتقال للخطوة التالية
     ▼
[8] SECURITY_DECLARATION             [AAWSM §3.1.1.2]
     │  - توقيع رقمي من ضابط أمن مخوَّل (role ∈ {SecurityOfficer, Supervisor, CSO})
     │  - يفشل تلقائيًا إن لم تكتمل المراحل 2-7 بحالة PASSED
     ▼
[9] SECURITY_CLEARANCE_EVALUATION (Rules Engine)
     │  - تقييم كل Blocking Conditions (انظر 06_security_rules.md)
     │  - PASS كل الشروط → Flights.security_status = CLEARED
     │  - أي شرط فاشل → BLOCKED + سبب مفصَّل + من يملك صلاحية Override
     ▼
[10] CLEARED / DEPARTED
```

## المسار الاستثنائي: EMERGENCY (لا يتبع التسلسل أعلاه)
مشغَّل من أي مرحلة عند: اكتشاف عنصر مشبوه، تهديد قنبلة، محاولة تدخل غير
مشروع. يوقف الـ Workflow العادي فورًا، يفتح جدول `emergency_events` منفصل،
ولا يُسمح بأي `CLEARED` للرحلة المرتبطة حتى إغلاق الحدث رسميًا من CSO/Supervisor
[AAWSM Ch.14].

## ✅ قرار محسوم (Waled، انظر 08_open_decisions.md #2)
1. **تسلسل [4] Catering و[5] Cargo: توازٍ (Parallel) — مؤكَّد.** عمليات
   الرامب الفعلية تتطلب تخليص الكاترينج والشحن في آن واحد خلال نافذة
   الـ Turnaround؛ هذا مطابق لما هو منفَّذ فعليًا في `workflow.py`
   (sequence_order=3 لكليهما).
2. لا يزال لا يوجد في الدليل SLA زمني صريح — بند مفتوح منفصل، لا يعيق التقدّم.
