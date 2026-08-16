import type { requestSetupEn } from './requestSetupEn';

export const requestSetupAr: Record<keyof typeof requestSetupEn, string> = {
  requestRulesSubtitle: 'قواعد للمواعيد والطلبات وطلبات الزبائن الأخرى.',
  requestRulesAdd: 'إضافة قاعدة طلب',
  requestRulesInfoTitle: 'ما هي قاعدة الطلب؟',
  requestRulesInfoBody:
    'علّم Linas كيف يتعامل مع موعد أو طلب أو أي طلب آخر. في الملاحظة، اكتب التفاصيل التي يجب جمعها والروابط التي يجب إرسالها. النتيجة تظهر في الطلبات.',
  requestRulesSearch: 'بحث قواعد الطلب',
  requestRulesFooter: 'كل قاعدة تستخدم أيقونة الطلب نفسها.',
  requestRulesEmpty: 'لا قواعد بعد — اضغط إضافة قاعدة طلب.',
  requestRulesUntitled: 'قاعدة بلا عنوان',
  requestRulesPublished: 'منشورة',
  requestRulesDraft: 'مسودة',
  requestRulesCollects: 'يجمع {fields}',
  requestRulesCollectsEmpty: 'لا حقول مُجمَّعة بعد',
  requestRulesEditTitle: 'تعديل قاعدة الطلب',
  requestRulesNote: 'ملاحظة لـ Linas',
  requestRulesNoteHint: 'اكتب التفاصيل التي يجب جمعها والروابط التي يجب إرسالها.',
  requestRulesSave: 'حفظ التغييرات',
  requestRulesNameRequired: 'أدخل عنواناً.',
  requestRulesDeleteTitle: 'حذف قاعدة الطلب هذه؟',
  requestRulesDeleteBody: 'سيتم حذف القاعدة من إعداد الذكاء.',
  requestRulesPreviewFailed: 'تعذّرت معاينة مخطط الطلب.',
  requestRulesPublishFailed: 'حُفظت المسودة، لكن نشر مخطط الطلب فشل.',
  requestRulesGraphLoadFailed: 'تعذّر تحميل مخططات الطلب المنشورة.',
  requestRulesDeleteGraphFailed: 'أُزيلت القاعدة من المسودة، لكن تعذّر حذف المخطط المنشور.',
};
