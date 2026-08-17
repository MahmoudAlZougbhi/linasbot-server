import { ISO639_LANGUAGE_CATALOG, type Iso639Lang } from './iso639Languages';

export type SmartAnswerLang = Iso639Lang;

/** Full world-language catalog (ISO 639-1 + franco). Prefer server catalog when available. */
const FALLBACK_CATALOG: SmartAnswerLang[] = ISO639_LANGUAGE_CATALOG;

let activeCatalog: SmartAnswerLang[] = FALLBACK_CATALOG;

/** @deprecated use getSmartAnswerLanguageCatalog */
export const SMART_ANSWER_LANGUAGE_CATALOG = FALLBACK_CATALOG;

export function setSmartAnswerLanguageCatalog(catalog: SmartAnswerLang[]): void {
  activeCatalog = catalog.length ? catalog : FALLBACK_CATALOG;
}

export function getSmartAnswerLanguageCatalog(): SmartAnswerLang[] {
  return activeCatalog;
}

/** @deprecated use getSmartAnswerLanguageCatalog */
export const FAQ_LANGS = FALLBACK_CATALOG.map((lang) => ({
  id: lang.id,
  labelKey: `faqLang_${lang.id}` as const,
}));

export type FaqLangId = string;

function findLang(langId: string): SmartAnswerLang | undefined {
  return activeCatalog.find((l) => l.id === langId) || FALLBACK_CATALOG.find((l) => l.id === langId);
}

export function langLabel(langId: string): string {
  return findLang(langId)?.label || langId;
}

export function langNativeLabel(langId: string): string {
  const hit = findLang(langId);
  return hit?.native || hit?.label || langId;
}

export function sortLangIds(ids: string[]): string[] {
  const order = activeCatalog.map((lang) => lang.id);
  return [...ids].sort((a, b) => {
    const ia = order.indexOf(a);
    const ib = order.indexOf(b);
    return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib);
  });
}

export const FAQ_ASK_LINAS_PROMPT =
  'Explain Smart Q&A: saved Q&A so when a customer asks the same question, the bot replies from FAQ instead of full AI generation — saving credits. Owner picks Smart Q&A languages from any world language; new Q&A auto-translates into those languages only. Customer reply language is separate (multilingual auto-detect). Help me add a Smart Q&A if I want.';
