/** Short natural affirmatives for pending CM / high-impact Draft approval. */
const OWNER_ASSENT_RE =
  /^\s*(ok|okay|okey|yes|yeah|yep|yup|sure|deal|done|confirm|approve|agreed?|go\s*ahead|do\s*it|save|agree(\s+to\s+save)?|approve(\s+(and\s+)?apply)?(\s+to\s+draft)?|تمام|اوكي|أوكي|اوك|أوك|ايه|نعم|اه|آه|تم|ماشي|حاضر|يلا|موافق|احفظ|نفذ|👍|✅)\s*[.!؟]*\s*$/iu;

export function looksLikeOwnerAssent(text: string): boolean {
  const t = (text || '').trim();
  if (!t || t.length > 80) return false;
  return OWNER_ASSENT_RE.test(t);
}

export function pendingTokenFromDonePayload(payload: Record<string, unknown>): string | null {
  const direct = payload.pending_confirmation;
  if (typeof direct === 'string' && direct.trim()) return direct.trim();
  const patch = payload.proposed_patch;
  if (patch && typeof patch === 'object') {
    const token = (patch as { confirmation_token?: unknown }).confirmation_token;
    if (typeof token === 'string' && token.trim()) return token.trim();
  }
  const cards = payload.cards;
  if (Array.isArray(cards)) {
    for (let i = cards.length - 1; i >= 0; i -= 1) {
      const card = cards[i] as { kind?: string; data?: { confirmation_token?: unknown } };
      if (card?.kind !== 'proposal') continue;
      const token = card.data?.confirmation_token;
      if (typeof token === 'string' && token.trim()) return token.trim();
    }
  }
  return null;
}
