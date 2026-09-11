/** @typedef {'en' | 'ar' | 'fr'} PublicLandingLocale */

/** @type {PublicLandingLocale[]} */
export const PUBLIC_LANDING_LOCALES = ['en', 'ar', 'fr'];

/** @type {Record<PublicLandingLocale, string>} */
export const PUBLIC_LANDING_LOCALE_LABELS = {
  en: 'EN',
  ar: 'ع',
  fr: 'FR',
};

const STORAGE_KEY = 'linas_public_lang';

/** @returns {PublicLandingLocale} */
export function readPublicLandingLocale() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'en' || stored === 'ar' || stored === 'fr') return stored;
  } catch {
    /* private mode */
  }
  const browser = (navigator.language || 'en').toLowerCase();
  if (browser.startsWith('ar')) return 'ar';
  if (browser.startsWith('fr')) return 'fr';
  return 'en';
}

/** @param {PublicLandingLocale} locale */
export function storePublicLandingLocale(locale) {
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    /* ignore */
  }
}

/** @param {PublicLandingLocale} locale */
export function applyPublicLandingLocaleToDocument(locale) {
  document.documentElement.lang = locale;
  document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr';
}
