# Requirements Matrix — مستخرجة من AAWSM (Rev01, 01.10.2021)

**ملاحظة منهجية:** الأعمدة أدناه لا تنسخ نص الدليل حرفيًا (لتفادي إعادة نشر
SSI) بل تحوّله إلى **متطلب نظامي قابل للتنفيذ**. مرجع كل بند مذكور برقم
الفصل/القسم [AAWSM §] ليعود إليه فريق المشروع في الدليل الأصلي. مستوى الثقة:
**High** = نص صريح في الدليل، **Medium** = استنتاج من عدة أقسام مترابطة.

| ID | الفئة | المتطلب (نظامي) | AAWSM § | إلزامي؟ | تأثير على النظام | ثقة |
|----|------|------------------|---------|---------|-------------------|-----|
| R-001 | Workflow | لكل رحلة مسار أمني إلزامي بترتيب محدد: قبول → فحص أمن الطائرة → أمن الأمتعة/المطابقة → أمن الكاترينج → التحقق من الأختام → مراجعة الحوادث → التصريح الأمني → Cleared | §2 (AVSEC-OMS legacy, يتطابق مع فلسفة Ch.4–9 من AAWSM) | نعم | Workflow Engine بحالات متسلسلة، لا يمكن تجاوز مرحلة | High |
| R-002 | Aircraft Security | فحص أمني للطائرة (Security Check/Search) قبل الخدمة، قبل كل إقلاع (Pre-flight)، وعند نقاط العبور، ووفق قائمة تفتيش خاصة بنوع الطائرة | AAWSM §8.0–8.2, Std 4.3.1 | نعم | Checklist ديناميكي بحسب `aircraft_type`، حقل PASS/FAIL لكل بند + توقيع رقمي | High |
| R-003 | Aircraft Security | نتيجة الفحص توقّع من: PIC/Flight Crew (Flight Deck)، Cabin Crew (Cabin)، Station Engineer (Cargo Holds) | AAWSM §8.2 | نعم | 3 توقيعات إلزامية دنيا لإغلاق Checklist الفحص | High |
| R-004 | Aircraft Security | عند اكتشاف عنصر مشبوه: إجراء "لا تلمس → إخلاء → عزل (Cordon) → تحكم بالوصول" وإبلاغ فوري | AAWSM §14.1.3 | نعم | حالة `SECURITY_INCIDENT` توقف الـ Workflow فورًا وتُنشئ حادثة مرتبطة إلزاميًا | High |
| R-005 | Baggage Security | مطابقة الركاب بالأمتعة (Baggage Reconciliation) إلزامية لكل رحلة (Originating/Transfer/Interline) | AAWSM Ch.7، Std 4.4.3 | نعم | لا يمكن تحميل حقيبة بلا راكب مطابق مسجَّل على الرحلة؛ حقل Reconciliation Count | High |
| R-006 | Baggage Security | فحص 100% من الأمتعة المسجَّلة (Hold Baggage) بإحدى الطرق المعتمدة (X-ray/EDS/يدوي/كلاب) | AAWSM §5.0.1, Std 4.5.1 | نعم | حقل `screening_method` + `screening_result` إلزامي لكل حقيبة/دفعة | High |
| R-007 | Baggage Security | الأمتعة غير المصحوبة (Unaccompanied/Rush) تُعامل كمرسل غير معروف، وتُفحص أو تُحجز 24 ساعة | AAWSM §7.3, §11.3 | نعم | Flag `unaccompanied=true` يفرض مسار فحص إضافي إلزامي قبل التحميل | High |
| R-008 | Catering Security | شحنات الكاترينج تُفحص/تُختم في المطبخ، وتُتحقق الأختام عند التسليم للطائرة، وأي كسر بالختم = فحص يدوي كامل إلزامي | AAWSM §9.2–9.3 | نعم | `seal_number` + `seal_status(intact/broken)` + إعادة فحص إلزامية عند broken | High |
| R-009 | Cargo Security | القبول لا يتم إلا من Regulated Agent/Known Consignor أو بعد فحص كامل لـ"Unknown Cargo" | AAWSM Ch.11, Std 4.6.2/4.6.4 | نعم | Flag `consignor_status(known/regulated/unknown)` يفرض `screening_required=true` عند unknown | High |
| R-010 | Access Control | لا وصول لمنطقة مقيدة (SRA) أو للطائرة إلا بترخيص ساري (ID Badge) وتحقق ظاهر أعلى الخصر | AAWSM §2.3.6, §8.3 | نعم | كل حدث تفتيش/تسليم يتطلب `officer_id` + `badge_verified=true` | High |
| R-011 | Incident Reporting | أي حادثة أمنية تُوثَّق كتابيًا (وقت، موقع، وصف، شهود، إجراء) وتُصعَّد فورًا للمشرف | AAWSM Ch.15 | نعم | جدول `security_incidents` إلزامي الحقول + إشعار Supervisor فوري | High |
| R-012 | Threat Levels | تصنيف التهديد 3 مستويات (Green/Amber/Red) يغيّر متطلبات كل إجراء (نسبة الفحص العشوائي، عدد الحراس..) | AAWSM §2.4, Ch.14.2 | نعم | حقل `threat_level` على مستوى المطار/الرحلة يُغيّر معاملات القواعد (rule parameters) لا القواعد نفسها | High |
| R-013 | Declaration | لا "Security Cleared" لرحلة إلا بعد تصريح أمني موقّع رقميًا من ضابط أمن مخوَّل | AAWSM §3.1.1.2 (AAW Security Declaration) | نعم | حالة نهائية `CLEARED` تتطلب `officer_signature` + استيفاء كل الـ Blocking Rules | High |
| R-014 | Roles | تسلسل هرمي: CSO → Superintendent → Supervisor → Security Officer → Security Guard، بصلاحيات متدرجة | AAWSM §3.4.1.6 | نعم | RBAC بـ 5 أدوار حد أدنى + صلاحية "Override" محصورة بـ CSO/Supervisor فقط مع سبب مسجَّل | High |
| R-015 | Special Categories | فئات خاصة (دبلوماسيون، مرحّلون، مسجونون مرافَقون، أسلحة مرخَّصة) تتطلب مسار موافقة إضافي وتوثيق | AAWSM §4.8, §4.10 | نعم | Flag `special_category` يفرض حقول توثيق إضافية + موافقة قبل الصعود | Medium |
| R-016 | Prohibited Items | قائمة أصناف محظورة معتمدة (وليست ثابتة أبديًا — تُحدَّث دوريًا من الجهة المنظمة) | AAWSM Appendix F, [تحقق خارجي مطلوب] | نعم | جدول `prohibited_items` قابل للتحديث الإداري دون تعديل كود | High (وجود القائمة) / Medium (تحديثها الدوري) |
| R-017 | Recruitment | لا تكليف بمهام أمنية إلا بعد Background Check موثّق وتدريب معتمد (BSC) وشهادة سارية | AAWSM Ch.12–13 | نعم | حقل `certification_expiry` على المستخدم يمنع تسجيل أي إجراء أمني بعد الانتهاء | High |
| R-018 | Quality Control | تدقيق دوري (Audit/Inspection/Test/Exercise/Survey) موثّق ومرتبط بإجراءات تصحيحية | AAWSM Ch.16 | نعم | جدول `audits` + `corrective_actions` مرتبط بـ `finding_id` | High |
| R-019 | Sealing | أختام أمنية للطائرة (Night-stop) بأرقام مسلسلة متتبَّعة، وأي كسر/فقدان يُبلَّغ فورًا | AAWSM Appendix I | نعم | جدول `aircraft_seals` بحالة (`intact/broken/missing`) + تنبيه تلقائي | High |
| R-020 | Contingency | إجراءات طوارئ مختلفة حسب نوع الحدث (تهديد قنبلة، اختطاف، اكتشاف عنصر مشبوه) بمستويات استجابة مختلفة | AAWSM Ch.14 | نعم | حالة `EMERGENCY` منفصلة عن الـ Workflow العادي، لا تُفرض عليها نفس قيود التسلسل | High |

## بنود تحتاج تحققًا خارجيًا (لم تُحسم بعد — انظر `07_research_log.md`)
- R-016: هل نسخة قائمة الأصناف المحظورة في الدليل (2021) لا تزال متوافقة مع
  متطلبات LCAA/ICAO الحالية (2026)؟ **لم يُتحقق بعد — يحتاج بحثًا موجّهًا.**
- إشارة الدليل إلى "Annex 17 ... Eleventh edition" — **تم التحقق أوليًا: النسخة
  الحادية عشرة لا تزال الإصدار الجاري لدى ICAO لكن بعدد تعديلات (Amendments)
  أحدث من 2021** — انظر سجل البحث. **لا يُغيَّر أي متطلب في الدليل تلقائيًا
  بناءً على هذا — يحتاج قرارك.**
