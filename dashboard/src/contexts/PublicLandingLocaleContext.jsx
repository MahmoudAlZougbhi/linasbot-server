import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import {
  applyPublicLandingLocaleToDocument,
  readPublicLandingLocale,
  storePublicLandingLocale,
} from '../constants/publicLandingLocale';

/** @typedef {import('../constants/publicLandingLocale').PublicLandingLocale} PublicLandingLocale */

const PublicLandingLocaleContext = createContext(
  /** @type {{ locale: PublicLandingLocale; setLocale: (next: PublicLandingLocale) => void } | undefined} */ (
    undefined
  ),
);

/** @param {{ children: import('react').ReactNode }} props */
export function PublicLandingLocaleProvider({ children }) {
  const [locale, setLocaleState] = useState(/** @type {PublicLandingLocale} */ ('en'));

  useEffect(() => {
    const initial = readPublicLandingLocale();
    setLocaleState(initial);
    applyPublicLandingLocaleToDocument(initial);
  }, []);

  const setLocale = (/** @type {PublicLandingLocale} */ next) => {
    setLocaleState(next);
    storePublicLandingLocale(next);
    applyPublicLandingLocaleToDocument(next);
  };

  const value = useMemo(
    () => ({
      locale,
      setLocale,
    }),
    [locale],
  );

  return (
    <PublicLandingLocaleContext.Provider value={value}>
      {children}
    </PublicLandingLocaleContext.Provider>
  );
}

export function usePublicLandingLocale() {
  const ctx = useContext(PublicLandingLocaleContext);
  if (!ctx) {
    throw new Error('usePublicLandingLocale must be used within PublicLandingLocaleProvider');
  }
  return ctx;
}
