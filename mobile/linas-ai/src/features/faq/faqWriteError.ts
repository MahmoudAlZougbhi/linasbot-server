import { ApiError, isDailyEditLimitError } from '../../api/client';
import type { StringKey } from '../../i18n/locales/en';

export function faqWriteErrorMessage(
  err: unknown,
  tr: (key: StringKey) => string,
  fallback: StringKey = 'faqCreateError',
): string {
  if (isDailyEditLimitError(err)) return tr('aiSetupDailyEditLimit');
  if (err instanceof ApiError && (err.status === 402 || err.status === 403)) return tr('faqQuotaUpgrade');
  if (err instanceof ApiError && err.message.trim()) return err.message;
  return tr(fallback);
}
