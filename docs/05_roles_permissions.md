# Roles & Permissions — مستخرجة من AAWSM §3.4.1.6 (Terms of Reference)

| الدور (Role) | مطابقة AAWSM | يمكنه تنفيذ Checklist | يمكنه فتح/إغلاق حادثة | يمكنه توقيع Declaration | Override لقاعدة حظر | إدارة المستخدمين/الأدوار | رفع نسخة دليل جديدة (V2) |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `SECURITY_GUARD` | Security Guard | ✅ (تنفيذي فقط) | ✅ (فتح فقط) | ❌ | ❌ | ❌ | ❌ |
| `SECURITY_OFFICER` | Security Officer | ✅ | ✅ | ✅ (إن مخوَّل صراحة) | ❌ | ❌ | ❌ |
| `SUPERVISOR` | Security Supervisor | ✅ | ✅ (فتح/إغلاق) | ✅ | ✅ (بسبب موثَّق إلزامي) | ❌ | ❌ |
| `SUPERINTENDENT` | Security Superintendent | ✅ (مراجعة) | ✅ | ✅ | ✅ | ✅ (ضمن فريقه) | ❌ |
| `CSO` | Chief Security Officer | عرض كامل | ✅ | ✅ | ✅ | ✅ | ✅ (V1: نسخة AAW فقط) |
| `PLATFORM_ADMIN` | (لا مقابل في AAWSM — دور منصّة تقني بحت) | ❌ تنفيذي | ❌ | ❌ | ❌ | ✅ (عابر لكل الشركات) | ✅ (كل الشركات — V2) |

## قواعد صارمة
1. **لا Override بدون سبب مكتوب + توثيق في Audit Trail** — لا استثناء
   [يستند إلى مبدأ Separation of Duties المذكور في §3.2.1.4/Quality Control
   Ch.16، Confidence: Medium — الدليل لا يستخدم مصطلح "Override" حرفيًا لكن
   مبدأ عدم تجاوز الفحوصات دون توثيق مستمَد من فلسفة QA الكاملة في الدليل].
2. `PLATFORM_ADMIN` **لا يمكنه إطلاقًا** تنفيذ أو توقيع أي إجراء أمني تشغيلي —
   دوره تقني/إداري بحت (هذا قرار هندسي مضاف من فريق المشروع، ليس من الدليل،
   لضمان فصل الصلاحيات التقنية عن التشغيلية).
3. كل حساب مستخدم أمني (Guard→CSO) يجب أن يحمل `certification_expiry` ساري
   [R-017] — النظام يمنع تسجيل أي إجراء إذا `certification_expiry < today`.
