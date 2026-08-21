/** Integrations account display + app version gate copy (ar). */
export const integrationsDisplayAr = {
  metaOAuthFailedFacebook: 'فشل تفويض Facebook. افصل Facebook ثم اربطه من جديد.',
  metaOAuthFailedFacebookScopes:
    'Facebook لم يمنح كل الصلاحيات المطلوبة، بما فيها business_management. اربطه مجدداً، واختر الـ Business والـ Page، واسمح بكل الصلاحيات.',
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
  metaOAuthFailedBusy:
    'عملية ربط Instagram أخرى لم تنتهِ بعد. انتظر قليلاً ثم اضغط Connect مرة واحدة.',
  metaOAuthFailedGuard:
    'تعذّر التحقق من حالة أمان ربط Instagram. انتظر قليلاً ثم حاول مجدداً.',
  metaOAuthFailedDeletionFailed:
    'تفويض Instagram محظور لأن طلب حذف بيانات Meta فشل. اطلب من المسؤول حلّ الطلب، ثم اربطه من جديد.',
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
