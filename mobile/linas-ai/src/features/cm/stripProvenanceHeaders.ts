/** Strip CM remigrate provenance headers from owner-facing text. */
const PROVENANCE_PREFIX = '--- redistributed from ';
const PROVENANCE_HEADER_RE = /--- redistributed from [\s\S]*? ---[ \t]*\n?/g;

const AI_BASICS_TEXT_FIELDS = [
  'greeting_behavior',
  'short_introduction',
  'identity_summary',
  'advanced_instructions',
] as const;

export function stripProvenanceHeaders(text: unknown): string {
  const raw = text == null ? '' : String(text);
  if (!raw.includes(PROVENANCE_PREFIX)) return raw;
  return raw.replace(PROVENANCE_HEADER_RE, '').trim();
}

export function sanitizeCmSectionPayload(
  section: string,
  payload: Record<string, unknown>,
): Record<string, unknown> {
  const name = section.trim().replace(/-/g, '_');
  const out = { ...payload };
  if (name === 'ai_basics') {
    for (const key of AI_BASICS_TEXT_FIELDS) {
      if (typeof out[key] === 'string') {
        out[key] = stripProvenanceHeaders(out[key]);
      }
    }
  } else if (name === 'style' && typeof out.style_body === 'string') {
    out.style_body = stripProvenanceHeaders(out.style_body);
  }
  return out;
}
