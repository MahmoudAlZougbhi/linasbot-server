/** @typedef {'en' | 'ar' | 'fr'} PublicLandingLocale */

/** @type {PublicLandingLocale[]} */
export const PUBLIC_LANDING_LOCALES = ['en', 'ar', 'fr'];

/** @type {Record<PublicLandingLocale, string>} */
export const PUBLIC_LANDING_LOCALE_LABELS = {
  en: 'EN',
  ar: 'ع',
  fr: 'FR',
};

/** @type {Record<PublicLandingLocale, { greeting: string; helping: string; annoyed: string; bored: string; laughing: string; ariaLabel: string; hint: string }>} */
export const MASCOT_SPEECH = {
  en: {
    greeting: "Hi! I'm Linas — your reply assistant 👋",
    helping: "Ok dear — I'll sort it out for you!",
    annoyed: 'Hey! Easy on the long press! 😤',
    bored: '*yawn*… waiting for customers…',
    laughing: 'Hehehe! 😄',
    ariaLabel: 'Linas, futuristic AI assistant character',
    hint: 'Linas — double-tap for help · long-press annoys him',
  },
  ar: {
    greeting: 'مرحبا! أنا Linas — مساعدك بالردود 👋',
    helping: 'تمام حبيبي — حاه ظبطلك!',
    annoyed: 'شو هالضغطة الطويلة؟! 😤',
    bored: '*تثاؤب*… عم انتظر الزبائن…',
    laughing: 'هيهيهي! 😄',
    ariaLabel: 'Linas، شخصية المساعد الذكي',
    hint: 'Linas — نقرتين للمساعدة · الضغط الطويل يزعجه',
  },
  fr: {
    greeting: 'Salut ! Je suis Linas — ton assistant réponses 👋',
    helping: "D'accord — je m'en occupe pour toi !",
    annoyed: 'Hé ! Pas de long press ! 😤',
    bored: '*bâillement*… en attente de clients…',
    laughing: 'Hihihi ! 😄',
    ariaLabel: 'Linas, personnage assistant IA futuriste',
    hint: 'Linas — double appui pour aider · appui long = énervé',
  },
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
