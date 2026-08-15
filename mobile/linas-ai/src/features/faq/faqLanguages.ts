export type SmartAnswerLang = {
  id: string;
  label: string;
  native?: string;
};

export const SMART_ANSWER_LANGUAGE_CATALOG: SmartAnswerLang[] = [
  { id: 'en', label: 'English', native: 'English' },
  { id: 'ar', label: 'Arabic', native: 'العربية' },
  { id: 'franco', label: 'Franco / Arabizi', native: 'Franco' },
  { id: 'fr', label: 'French', native: 'Français' },
  { id: 'es', label: 'Spanish', native: 'Español' },
  { id: 'de', label: 'German', native: 'Deutsch' },
  { id: 'it', label: 'Italian', native: 'Italiano' },
  { id: 'pt', label: 'Portuguese', native: 'Português' },
  { id: 'zh', label: 'Chinese', native: '中文' },
  { id: 'tr', label: 'Turkish', native: 'Türkçe' },
  { id: 'ru', label: 'Russian', native: 'Русский' },
];

/** @deprecated use SMART_ANSWER_LANGUAGE_CATALOG */
export const FAQ_LANGS = SMART_ANSWER_LANGUAGE_CATALOG.map((lang) => ({
  id: lang.id,
  labelKey: `faqLang_${lang.id}` as const,
}));

export type FaqLangId = string;

export function langLabel(langId: string): string {
  const hit = SMART_ANSWER_LANGUAGE_CATALOG.find((l) => l.id === langId);
  return hit?.label || langId;
}

export const FAQ_ASK_LINAS_PROMPT =
  'Explain Smart Q&A: saved Q&A so when a customer asks the same question, the bot replies from FAQ instead of full AI generation — saving credits. Owner picks Smart Q&A languages; new Q&A auto-translates into those languages only. Customer reply language is separate (multilingual auto-detect). Help me add a Smart Q&A if I want.';
