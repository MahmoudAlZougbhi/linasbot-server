export const FAQ_LANGS = [
  { id: 'ar', labelKey: 'faqLangAr' as const },
  { id: 'en', labelKey: 'faqLangEn' as const },
  { id: 'fr', labelKey: 'faqLangFr' as const },
  { id: 'franco', labelKey: 'faqLangFranco' as const },
] as const;

export type FaqLangId = (typeof FAQ_LANGS)[number]['id'];

export const FAQ_ASK_LINAS_PROMPT =
  'Explain Smart Answers / FAQ: ready-made Q&A so when a customer asks the same question or same meaning, the bot replies from FAQ instead of a full AI generation — that saves AI credits. Entries auto-translate to Arabic, English, French, and Franco. Then help me add a Smart Answer if I want (propose for my Approve).';
