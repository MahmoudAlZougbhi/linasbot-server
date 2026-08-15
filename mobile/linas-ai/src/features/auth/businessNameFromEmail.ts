/** Derive register `business_name` from email — the API still requires 2–120 chars. */
export function businessNameFromEmail(email: string): string {
  const trimmed = email.trim();
  const local = (trimmed.split('@')[0] || '').replace(/[._+-]+/g, ' ').trim();
  const cleaned = local.replace(/\s+/g, ' ').slice(0, 120);
  if (cleaned.length >= 2) return cleaned;
  const domain = (trimmed.split('@')[1] || 'account').split('.')[0] || 'account';
  const combined = `${cleaned} ${domain}`.trim().slice(0, 120);
  return combined.length >= 2 ? combined : 'My account';
}
