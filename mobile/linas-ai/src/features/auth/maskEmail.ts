/** Mask local-part after the first character: m•••••@example.com */
export function maskEmail(email: string): string {
  const trimmed = email.trim();
  const at = trimmed.indexOf('@');
  if (at < 1) return trimmed;
  const local = trimmed.slice(0, at);
  const domain = trimmed.slice(at);
  return `${local[0]}${'•'.repeat(5)}${domain}`;
}
