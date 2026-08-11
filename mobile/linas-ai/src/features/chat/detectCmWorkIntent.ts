/**
 * Heuristic: owner message is about Content Manager / CM sections.
 * Used to auto-switch Chat → Work (5.6 LIN High) before send.
 * Keep in sync with services.model_policy.looks_like_cm_work_intent.
 */
const CM_WORK_INTENT =
  /\b(content\s*management|content\s*manager|content-manager|\bcm\b)\b|\b(faq|smart\s*answers?|knowledge|handoff|publish|draft|validate)\b|\b(opening\s*hours?|business\s*hours?|working\s*hours?|off\s*days?)\b|\b(ai\s*basics|ai\s*limits|dynamic\s*messages|care\s*instructions|response\s*style|ai\s*style)\b|\b(prices?|branches?|services?|languages?|restricted|sections?)\b|(إدارة\s*المحتوى|كونتنت|محتوى)|(\bFAQ\b|أسئلة\s*شائعة|سؤال\s*وجواب)|(ساعات\s*(العمل|الدوام)?|مواعيد\s*(العمل|الدوام)?|دوام)|(معرفة|انشر|نشر|أسعار|فروع|خدمات|أسئلة)/i;

export function detectCmWorkIntent(text: string | null | undefined): boolean {
  const raw = (text || '').trim();
  if (!raw) return false;
  return CM_WORK_INTENT.test(raw);
}
