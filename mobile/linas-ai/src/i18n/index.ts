import { I18nManager } from 'react-native';

import { ar } from './locales/ar';
import { en, type StringKey } from './locales/en';
import { fr } from './locales/fr';

export type AppLanguage = 'en' | 'ar' | 'fr';

const TABLES: Record<AppLanguage, Record<StringKey, string>> = {
  en: en as Record<StringKey, string>,
  ar,
  fr,
};

export function normalizeLanguage(value: string | null | undefined): AppLanguage {
  const raw = (value || 'en').toLowerCase();
  if (raw.startsWith('ar')) return 'ar';
  if (raw.startsWith('fr')) return 'fr';
  return 'en';
}

export function t(lang: AppLanguage, key: StringKey): string {
  return TABLES[lang][key] ?? TABLES.en[key] ?? key;
}

export function isRtl(lang: AppLanguage): boolean {
  return lang === 'ar';
}

/** Apply RTL layout when Arabic is selected. May require reload on some devices. */
export function applyRtl(lang: AppLanguage): void {
  const rtl = isRtl(lang);
  if (I18nManager.isRTL !== rtl) {
    I18nManager.allowRTL(rtl);
    I18nManager.forceRTL(rtl);
  }
}

export type { StringKey };
