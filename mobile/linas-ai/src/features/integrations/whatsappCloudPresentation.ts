export type WhatsAppConnectionPresentation = {
  connection_source?: 'embedded_signup' | 'meta_app_review_test';
  display_phone_number?: string;
  display_phone_last4?: string;
  verified_name?: string;
};

export function whatsappConnectionSubtitle(
  connection: WhatsAppConnectionPresentation | null | undefined,
  fallback: string,
): string {
  const name = connection?.verified_name?.trim() || '';
  const number = connection?.display_phone_number?.trim() || '';
  const last4 = connection?.display_phone_last4?.trim() || '';
  if (name && number) return `${name} · ${number}`;
  if (number) return number;
  if (name && last4) return `${name} · ••••${last4}`;
  if (name) return name;
  if (last4) return `••••${last4}`;
  return fallback;
}

export function isWhatsAppAppReviewTest(
  connection: WhatsAppConnectionPresentation | null | undefined,
): boolean {
  return connection?.connection_source === 'meta_app_review_test';
}

export function normalizeWhatsAppRecipient(value: string): string | null {
  const raw = String(value || '').trim();
  if (!raw || !/^[+\d\s()-]+$/.test(raw)) return null;
  if ((raw.match(/\+/g) || []).length > 1 || (raw.includes('+') && !raw.startsWith('+'))) return null;
  const digits = raw.replace(/[+\s()-]/g, '');
  return /^[1-9]\d{7,14}$/.test(digits) ? digits : null;
}

export function whatsappApiErrorDetail(error: unknown): string | null {
  if (!error || typeof error !== 'object') return null;
  const localMessage = (error as { message?: unknown }).message;
  const usefulLocalMessage =
    typeof localMessage === 'string' &&
    localMessage.trim() &&
    localMessage.trim() !== 'Request failed'
      ? localMessage.trim()
      : null;
  const body = (error as { body?: unknown }).body;
  if (!body || typeof body !== 'object') return usefulLocalMessage;
  const candidate = body as { message?: unknown; detail?: unknown; error?: unknown };
  for (const value of [candidate.message, candidate.detail, candidate.error]) {
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return usefulLocalMessage;
}
