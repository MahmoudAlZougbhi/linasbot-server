import { ApiError, isDailyEditLimitError } from '../../api/client';
import type { StringKey } from '../../i18n';

export function mediaUploadErrorMessage(
  err: unknown,
  tr: (key: StringKey) => string,
  keys: { tooLarge: StringKey; unsupported: StringKey; fallback: StringKey },
): string {
  if (isDailyEditLimitError(err)) return tr('aiSetupDailyEditLimit');
  const detail =
    err instanceof ApiError && err.body && typeof err.body === 'object' && 'detail' in err.body
      ? JSON.stringify((err.body as { detail: unknown }).detail)
      : err instanceof Error
        ? err.message
        : '';
  if (detail.includes('file_too_large')) return tr(keys.tooLarge);
  if (detail.includes('unsupported_mime')) return tr(keys.unsupported);
  return tr(keys.fallback);
}
