# Security Rules & Blocking Conditions

هذه القواعد تُنفَّذ حرفيًا في `backend/app/rules/engine.py` وتُخزَّن معرَّفة في
جدول `security_rules` (قابلة للتعديل الإداري دون نشر كود جديد — حسب مبدأ
Multi-tenant في `01_architecture.md`).

| Rule ID | الشرط | المصدر | الأثر عند الفشل | يمكن Override؟ |
|---|---|---|---|---|
| BR-01 | `aircraft_check.status != PASSED` | AAWSM §8.2 | يمنع `CLEARED` نهائيًا | ❌ (يجب إعادة الفحص) |
| BR-02 | `baggage_reconciliation.mismatch_count > 0` | AAWSM Ch.7, Std 4.4.3 | يمنع `CLEARED` | ❌ |
| BR-03 | `open_incidents(severity IN (MAJOR,CRITICAL)).count > 0` | AAWSM Ch.15 | يمنع `CLEARED` | ✅ فقط CSO، بسبب موثَّق |
| BR-04 | `catering.seal_status = BROKEN AND manual_inspection.done = false` | AAWSM §9.3 | يمنع الانتقال لمرحلة Declaration | ❌ |
| BR-05 | `cargo.consignor_status = UNKNOWN AND screening.done = false` | AAWSM Ch.11, Std 4.6.4 | يمنع قبول الشحنة على الرحلة | ❌ |
| BR-06 | `aircraft_seal.status IN (BROKEN, MISSING)` | Appendix I | يفتح حادثة أمنية تلقائيًا + يمنع `CLEARED` حتى إغلاقها | ✅ Supervisor+ فقط، **بشرط سبب موثَّق + صورة دليل (evidence_url) إلزامية** [قرار Waled #3، 08_open_decisions.md] |
| BR-07 | `declaring_officer.certification_expiry < NOW()` | AAWSM Ch.12–13 | يمنع توقيع Declaration | ❌ |
| BR-08 | `declaring_officer.role NOT IN (SECURITY_OFFICER, SUPERVISOR, SUPERINTENDENT, CSO)` | AAWSM §3.4.1.6 | يمنع توقيع Declaration | ❌ |
| BR-09 | `emergency_event.status = OPEN (linked to flight)` | AAWSM Ch.14 | يمنع أي انتقال ضمن الـ Workflow العادي | ❌ (فقط إغلاق EMERGENCY رسميًا) |
| BR-10 | `threat_level = RED AND random_screening_pct < required_pct(RED)` | AAWSM §2.4, Ch.14.2 (Threat Matrix) | يمنع إغلاق مرحلة Screening | ❌ |

## آلية Override
- كل Override يُسجَّل في `audit_log` بحقول إلزامية: `rule_id`, `overridden_by`,
  `reason (نص حر إلزامي، لا يمكن حفظه فارغًا)`, `timestamp`, `linked_incident_id`
  (إن وُجد).
- لا يوجد Override "صامت" — أي تجاوز لقاعدة يُنتج سجلًا مرئيًا للمشرف الأعلى
  فورًا (Dashboard alert).

## ⚠️ قرار محسوم (Waled، انظر 08_open_decisions.md #3)
- **BR-06** يسمح بـ Override من Supervisor/Superintendent/CSO، **بشرط إلزامي
  إضافي: إرفاق `evidence_url` (صورة الختم التالف)** بجانب نص السبب. الطلب
  يُرفض في طبقة الـ API لو كان `rule_id == 'BR-06'` و`evidence_url` فارغ.
- **BR-03** يبقى كما هو (CSO فقط، سبب نصي دون صورة إلزامية — لم يُطلب تغييره).
