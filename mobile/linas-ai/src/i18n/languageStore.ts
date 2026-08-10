import type { AppLanguage } from './index';

/** Module-level app locale for API headers (LanguageContext keeps React state in sync). */
let currentLanguage: AppLanguage = 'en';

export function setStoredAppLanguage(lang: AppLanguage): void {
  currentLanguage = lang;
}

export function getStoredAppLanguage(): AppLanguage {
  return currentLanguage;
}
