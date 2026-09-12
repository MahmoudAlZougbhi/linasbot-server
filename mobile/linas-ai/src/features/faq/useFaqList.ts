import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError } from '../../api/client';
import { cacheGet, cacheInvalidate, cacheSet, isCacheFresh } from '../../cache/queryCache';
import { queryKeys } from '../../cache/queryKeys';
import { QUERY_TTL } from '../../cache/queryTtl';
import {
  listFaq,
  type FaqEntitlement,
  type FaqGroup,
} from './faqApi';
import { setSmartAnswerLanguageCatalog, type SmartAnswerLang } from './faqLanguages';

type FaqSnapshot = {
  items: FaqGroup[];
  entitlement: FaqEntitlement | null;
  smartAnswerLanguages: string[];
  catalog: SmartAnswerLang[];
};

export function useFaqList(tr: (key: 'faqLoadError') => string) {
  const cached = cacheGet<FaqSnapshot>(queryKeys.faq(''));
  const [loading, setLoading] = useState(!cached);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(Boolean(cached));
  const hasLoadedOnceRef = useRef(Boolean(cached));
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<FaqGroup[]>(cached?.data.items ?? []);
  const [entitlement, setEntitlement] = useState<FaqEntitlement | null>(cached?.data.entitlement ?? null);
  const [smartAnswerLanguages, setSmartAnswerLanguages] = useState<string[]>(
    cached?.data.smartAnswerLanguages ?? [],
  );
  const [languageCatalog, setLanguageCatalog] = useState<SmartAnswerLang[]>(cached?.data.catalog ?? []);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<FaqGroup | null>(null);

  const load = useCallback(async (opts?: { force?: boolean }) => {
    const q = query.trim();
    const key = queryKeys.faq(q);
    const hit = cacheGet<FaqSnapshot>(key);
    if (hit) {
      setItems(hit.data.items);
      setEntitlement(hit.data.entitlement);
      setSmartAnswerLanguages(hit.data.smartAnswerLanguages);
      if (hit.data.catalog.length) {
        setLanguageCatalog(hit.data.catalog);
        setSmartAnswerLanguageCatalog(hit.data.catalog);
      }
      hasLoadedOnceRef.current = true;
      setHasLoadedOnce(true);
      setLoading(false);
    }
    if (!opts?.force && hit && isCacheFresh(key, QUERY_TTL.faq)) return;
    if (!hasLoadedOnceRef.current) setLoading(true);
    setError(null);
    try {
      const data = await listFaq({ q: q || undefined });
      setItems(data.items);
      setEntitlement(data.entitlement);
      setSmartAnswerLanguages(data.smartAnswerLanguages);
      if (data.catalog.length) {
        setLanguageCatalog(data.catalog);
        setSmartAnswerLanguageCatalog(data.catalog);
      }
      cacheSet(key, {
        items: data.items,
        entitlement: data.entitlement,
        smartAnswerLanguages: data.smartAnswerLanguages,
        catalog: data.catalog,
      });
      setSelected((prev) => {
        if (!prev) return null;
        return data.items.find((g) => g.qa_group_id === prev.qa_group_id) || null;
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : tr('faqLoadError'));
    } finally {
      hasLoadedOnceRef.current = true;
      setLoading(false);
      setHasLoadedOnce(true);
    }
  }, [query, tr]);

  useEffect(() => {
    const handle = setTimeout(() => {
      void load();
    }, query ? 280 : 0);
    return () => clearTimeout(handle);
  }, [load, query]);

  const reloadAfterWrite = useCallback(async () => {
    cacheInvalidate(queryKeys.faqAll());
    await load({ force: true });
  }, [load]);

  return {
    loading,
    hasLoadedOnce,
    error,
    setError,
    items,
    entitlement,
    smartAnswerLanguages,
    setSmartAnswerLanguages,
    languageCatalog,
    query,
    setQuery,
    selected,
    setSelected,
    load,
    reloadAfterWrite,
  };
}
