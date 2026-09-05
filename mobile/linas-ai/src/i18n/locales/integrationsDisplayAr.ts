/** Integrations account display + app version gate copy (ar). */
export const integrationsDisplayAr = {
  metaOAuthFailedFacebook: 'فشل تفويض Facebook. اضغط Connect للمحاولة من جديد.',
  metaOAuthFailedFacebookScopes:
    'Facebook لم يمنح كل الصلاحيات المطلوبة، بما فيها business_management. امنح هذا الحساب وصولاً إلى الـ Page واسمح بكل الصلاحيات المطلوبة، ثم اضغط Connect من جديد.',
  metaOAuthFailedFacebookToken:
    'Meta رفض رمز تفويض Facebook. اربط Facebook من جديد.',
  metaOAuthFailedFacebookWebhook:
    'تم ربط Facebook، لكن إعداد الـ webhook لم يكتمل. اربطه مجدداً بعد دقيقة.',
  metaOAuthFailedFacebookDeletion:
    'تفويض Facebook محظور بسبب طلب حذف بيانات Meta معلّق.',
  metaOAuthFailedFacebookDeletionFailed:
    'تفويض Facebook محظور لأن طلب حذف بيانات Meta فشل. اطلب من المسؤول حلّ الطلب، ثم اربطه من جديد.',
  metaOAuthFailedFacebookBusy:
    'عملية ربط Facebook أخرى لم تنتهِ بعد. انتظر قليلاً ثم اضغط Connect مرة واحدة.',
  metaOAuthFailedFacebookGuard:
    'تعذّر التحقق من حالة أمان ربط Facebook. انتظر قليلاً ثم حاول مجدداً.',
  metaOAuthFailedFacebookConfig:
    'Facebook Login غير جاهز على السيرفر بعد. جرّب بعد آخر تحديث.',
  metaOAuthFailedFacebookConflict:
    'صفحة Facebook هذه مربوطة بمساحة عمل أخرى.',
  metaOAuthFailedFacebookNoPage:
    'لا توجد Page مؤهلة على Facebook. امنح الحساب وصولاً إلى رسائل الـ Page ونشاط المجتمع (أو تحكماً كاملاً)، ثم اضغط Connect من جديد.',
  metaOAuthFailedBusy:
    'عملية ربط Instagram أخرى لم تنتهِ بعد. انتظر قليلاً ثم اضغط Connect مرة واحدة.',
  metaOAuthFailedGuard:
    'تعذّر التحقق من حالة أمان ربط Instagram. انتظر قليلاً ثم حاول مجدداً.',
  metaOAuthFailedDeletionFailed:
    'تفويض Instagram محظور لأن طلب حذف بيانات Meta فشل. اطلب من المسؤول حلّ الطلب، ثم اربطه من جديد.',
  metaOAuthFailedProvider:
    'إنستغرام لم يؤكد إعداد الـ webhook بعد محاولتين. لا تضغط Connect من جديد. أرسل هذه الرسالة.',
  metaOAuthFailedRateLimit:
    'إنستغرام حدّ إعداد الـ webhook (خطأ Graph 613). لا تضغط Connect من جديد. أرسل هذه الرسالة.',
  integrationStatusConnected: 'الاتصال سليم',
  integrationStatusNeedsReconnect: 'يحتاج إعادة ربط',
  integrationStatusError: 'مشكلة في الاتصال',
  integrationLastSynced: 'آخر مزامنة',
  integrationReconnect: 'إعادة الربط',
  integrationConnectedFeatures: 'الميزات المتصلة',
  integrationMessengerReplies: 'ردود Messenger',
  integrationDmReplies: 'ردود الرسائل',
  integrationCommentReplies: 'ردود التعليقات',
  integrationFeatureOn: 'مفعّل',
  integrationFeatureOff: 'معطّل',
  integrationToggleMessages: 'الرسائل',
  integrationRefreshStatus: 'تحديث الحالة',
  integrationDisconnectAccount: 'فصل الحساب',
  integrationDisconnectHint: 'تتوقف ردود الذكاء الاصطناعي حتى تعيد الربط.',
  integrationWhatsAppHandle: 'رقم الأعمال',
  integrationStatusConnecting: 'جارٍ الربط',
  integrationStatusPermissionRequired: 'صلاحية مطلوبة',
  integrationStatusTokenExpired: 'انتهت صلاحية الرمز',
  integrationStatusPasswordChanged: 'تغيرت كلمة المرور — أعد الربط',
  integrationPasswordChangedReconnect:
    'تم تغيير كلمة مرور الحساب أو جلسة تسجيل الدخول. انفصل الربط. يرجى إعادة الربط.',
  integrationPasswordChangeHint:
    'إذا غيّرت كلمة مرور هذا الحساب، ينفصل الربط. اربطه من جديد لاستعادة الردود.',
  tiktokMessagingPending: 'رسائل TikTok معلّقة بانتظار موافقة TikTok Business Messaging.',
  tiktokLastSyncNever: 'لم تتم المزامنة بعد',
  drawerRecents: 'الأخيرة',
  drawerPin: 'مثبّت',
  appUpdateForceTitle: 'التحديث مطلوب',
  appUpdateForceBody:
    'الإصدار ({min}) لم يعد مدعوماً. ثبّت {latest} أو أحدث لمتابعة استخدام Linas AI.',
  appUpdateAvailableTitle: 'تحديث متاح',
  appUpdateAvailableBody: 'الإصدار {latest} متاح على App Store / Play Store.',
  appUpdateOpenStore: 'التحديث من المتجر',
  appUpdateDismiss: 'ليس الآن',
} as const;
