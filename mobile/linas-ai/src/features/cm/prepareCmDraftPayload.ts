import { normalizeBranchesDraftPayload } from './editors/locationOpeningHours/branchDraftNormalize';
import { sanitizeCmSectionPayload } from './stripProvenanceHeaders';

/** Sanitize + section-specific normalize before baseline / dirty snapshot. */
export function prepareCmDraftPayload(
  section: string,
  payload: Record<string, unknown>,
): Record<string, unknown> {
  const cleaned = sanitizeCmSectionPayload(section, payload);
  const name = section.trim().replace(/-/g, '_');
  if (name === 'branches') return normalizeBranchesDraftPayload(cleaned);
  return cleaned;
}
