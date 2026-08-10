import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { applyRtl, normalizeLanguage, t, type AppLanguage, type StringKey } from './index';
import { setStoredAppLanguage } from './languageStore';
import { syncPreferredLanguageToServer } from './syncPreferredLanguage';

const STORAGE_KEY = 'linas.ai.preferredLanguage';

type Ctx = {
  language: AppLanguage;
  setLanguage: (lang: AppLanguage) => void;
  tr: (key: StringKey) => string;
  isRtl: boolean;
};

const LanguageContext = createContext<Ctx | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<AppLanguage>('en');

  useEffect(() => {
    setStoredAppLanguage('en');
    void AsyncStorage.getItem(STORAGE_KEY).then((raw) => {
      if (raw) {
        const lang = normalizeLanguage(raw);
        setLanguageState(lang);
        setStoredAppLanguage(lang);
        applyRtl(lang);
      }
    });
  }, []);

  const setLanguage = (lang: AppLanguage) => {
    setLanguageState(lang);
    setStoredAppLanguage(lang);
    applyRtl(lang);
    void AsyncStorage.setItem(STORAGE_KEY, lang);
    void syncPreferredLanguageToServer(lang);
  };

  const value = useMemo(
    () => ({
      language,
      setLanguage,
      tr: (key: StringKey) => t(language, key),
      isRtl: language === 'ar',
    }),
    [language],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(LanguageContext);
  if (!ctx) {
    throw new Error('useI18n requires LanguageProvider');
  }
  return ctx;
}
