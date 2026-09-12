import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text } from 'react-native';

import { ApiError, isDailyEditLimitError } from '../../api/client';
import { cacheGet, cacheSet, dedupeFetch, isCacheFresh } from '../../cache/queryCache';
import { queryKeys } from '../../cache/queryKeys';
import { QUERY_TTL } from '../../cache/queryTtl';
import { EmptyState } from '../../components/EmptyState';
import { ScreenSkeleton } from '../../components/ScreenSkeleton';
import { useI18n } from '../../i18n/LanguageContext';
import { spacing, useTheme } from '../../theme';
import { fetchProducts } from '../products/productsApi';
import { ScreenChrome } from '../shared/ScreenChrome';
import { AiSetupFilterTabs, type AiSetupFilter } from './AiSetupFilterTabs';
import { AiSetupHubSections } from './AiSetupHubSections';
import { AiSetupProgressCard } from './AiSetupProgressCard';
import { fetchCmMeta, publishCmLive, unpublishCmLive, type CmMeta } from './cmApi';
import {
  buildFillMissingPrompt,
  fetchCmSetupProgress,
  summarizeHubProgress,
  type CmProgressRow,
} from './cmProgressApi';
import { CM_HUB_CARDS, type CmSectionId } from './cmSections';
import { cmSectionTitleKey } from './cmSectionTitles';

type Props = {
  onOpenSection: (section: CmSectionId) => void;
  onOpenProducts?: () => void;
  onContinueSetup?: (prompt: string) => void;
};

type CmHubSnapshot = {
  meta: CmMeta;
  rows: CmProgressRow[];
  productsComplete: boolean;
  live: boolean;
};

/** CM overview — design handoff layout with live progress + section grid. */
export function CmScreen({ onOpenSection, onOpenProducts, onContinueSetup }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const cached = cacheGet<CmHubSnapshot>(queryKeys.cmHub());
  const [loading, setLoading] = useState(!cached);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(Boolean(cached));
  const hasLoadedOnceRef = useRef(Boolean(cached));
  const [hydrated, setHydrated] = useState(Boolean(cached));
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<CmMeta | null>(cached?.data.meta ?? null);
  const [rows, setRows] = useState<CmProgressRow[]>(cached?.data.rows ?? []);
  const [productsComplete, setProductsComplete] = useState(cached?.data.productsComplete ?? false);
  const [live, setLive] = useState(cached?.data.live ?? false);
  const [liveBusy, setLiveBusy] = useState(false);
  const [filter, setFilter] = useState<AiSetupFilter>('all');

  const reload = useCallback(async (opts?: { force?: boolean }) => {
    const key = queryKeys.cmHub();
    const hit = cacheGet<CmHubSnapshot>(key);
    if (hit) {
      setMeta(hit.data.meta);
      setRows(hit.data.rows);
      setProductsComplete(hit.data.productsComplete);
      setLive(hit.data.live);
      setHydrated(true);
      hasLoadedOnceRef.current = true;
      setHasLoadedOnce(true);
      setLoading(false);
    }
    if (!opts?.force && hit && isCacheFresh(key, QUERY_TTL.cmHub)) return;
    if (!hasLoadedOnceRef.current) setLoading(true);
    try {
      const snapshot = await dedupeFetch(key, async () => {
        const [metaRes, prog, productsRes] = await Promise.all([
          fetchCmMeta(),
          fetchCmSetupProgress(),
          fetchProducts().catch(() => ({ products: [], total: 0 })),
        ]);
        return {
          meta: metaRes,
          rows: prog.progress ?? [],
          productsComplete: (productsRes.total ?? productsRes.products.length) > 0,
          live: Boolean(prog.summary?.published ?? metaRes.has_published_content),
        } satisfies CmHubSnapshot;
      });
      cacheSet(key, snapshot);
      setMeta(snapshot.meta);
      const progressRows = snapshot.rows;
      setRows(progressRows);
      setProductsComplete(snapshot.productsComplete);
      setLive(snapshot.live);
      setHydrated(true);
      setError(null);
    } catch {
      if (!hit) setError(tr('aiSetupLoadError'));
    } finally {
      hasLoadedOnceRef.current = true;
      setLoading(false);
      setHasLoadedOnce(true);
    }
  }, [tr]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const statusBySection = useMemo(() => {
    const map = new Map<string, 'complete' | 'incomplete'>();
    for (const row of rows) map.set(row.section, row.status);
    return map;
  }, [rows]);

  const displaySummary = useMemo(
    () => summarizeHubProgress(rows, { productsComplete }),
    [rows, productsComplete],
  );

  const tiles = useMemo(() => {
    const apiSections = new Set((meta?.sections ?? []).map((s) => s.replace(/-/g, '_')));
    const base =
      apiSections.size === 0
        ? CM_HUB_CARDS
        : CM_HUB_CARDS.filter((card) => apiSections.has(card.id));
    return base.filter((t) => {
      if (filter === 'missing') {
        const st = statusBySection.get(t.id);
        if (st === 'complete') return false;
      }
      return true;
    });
  }, [meta, filter, statusBySection]);

  const titleMap = useMemo(
    () => Object.fromEntries(CM_HUB_CARDS.map((c) => [c.id, tr(cmSectionTitleKey(c.id))])),
    [tr],
  );

  const applyLiveToggle = useCallback(
    async (nextLive: boolean) => {
      setLiveBusy(true);
      try {
        if (nextLive) {
          await publishCmLive('ai_setup_live_toggle');
          setLive(true);
        } else {
          await unpublishCmLive();
          setLive(false);
        }
        await reload();
      } catch (err) {
        const detail =
          err instanceof ApiError && typeof err.body === 'object' && err.body
            ? String(
                (err.body as { message?: string; detail?: string; error?: string }).message ||
                  (err.body as { detail?: string }).detail ||
                  (err.body as { error?: string }).error ||
                  '',
              )
            : '';
        Alert.alert(
          tr('aiSetupLiveToggleFailedTitle'),
          isDailyEditLimitError(err)
            ? tr('aiSetupDailyEditLimit')
            : detail.trim() || tr('aiSetupLiveToggleFailedBody'),
        );
      } finally {
        setLiveBusy(false);
      }
    },
    [reload, tr],
  );

  const onToggleLive = useCallback(() => {
    if (liveBusy) return;
    if (live) {
      Alert.alert(tr('aiSetupTurnOffAiTitle'), tr('aiSetupTurnOffAiBody'), [
        { text: tr('aiSetupCancel'), style: 'cancel' },
        {
          text: tr('aiSetupTurnOffAiConfirm'),
          style: 'destructive',
          onPress: () => void applyLiveToggle(false),
        },
      ]);
      return;
    }
    if (meta?.publish_enabled === false) {
      Alert.alert(
        tr('aiSetupLiveToggleFailedTitle'),
        meta.publish_disabled_message || tr('aiSetupLiveToggleFailedBody'),
      );
      return;
    }
    Alert.alert(tr('aiSetupTurnOnAiTitle'), tr('aiSetupTurnOnAiBody'), [
      { text: tr('aiSetupCancel'), style: 'cancel' },
      { text: tr('aiSetupTurnOnAiConfirm'), onPress: () => void applyLiveToggle(true) },
    ]);
  }, [applyLiveToggle, live, liveBusy, meta, tr]);

  return (
    <ScreenChrome title={tr('aiSetupTitle')}>
      {loading && !hasLoadedOnce ? (
        <>
          <AiSetupFilterTabs
            filter={filter}
            missingCount={0}
            onChange={setFilter}
          />
          <ScreenSkeleton variant="cards" rows={6} />
        </>
      ) : null}
      {hasLoadedOnce && error ? <Text style={{ color: colors.danger }}>{error}</Text> : null}
      {hasLoadedOnce && hydrated ? (
        <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
          <AiSetupProgressCard
            percent={displaySummary.percent}
            complete={displaySummary.complete}
            total={displaySummary.total}
            live={live}
            liveBusy={liveBusy}
            incomplete={displaySummary.incomplete}
            onToggleLive={onToggleLive}
            onContinueSetup={
              onContinueSetup
                ? () =>
                    onContinueSetup(
                      buildFillMissingPrompt(displaySummary.missing_sections, titleMap),
                    )
                : undefined
            }
            editsUsed={meta?.ai_setup_edits?.used}
            editsLimit={meta?.ai_setup_edits?.limit}
            editsReset={meta?.ai_setup_edits?.reset_at}
          />

          <AiSetupFilterTabs
            filter={filter}
            missingCount={displaySummary.incomplete}
            onChange={setFilter}
          />

          <AiSetupHubSections
            tiles={tiles}
            statusBySection={statusBySection}
            onOpenSection={onOpenSection}
            onOpenProducts={onOpenProducts}
          />

          {!loading && !meta && !error ? (
            <EmptyState title={tr('aiSetupUnavailable')} body={tr('aiSetupUnavailableBody')} />
          ) : null}
        </ScrollView>
      ) : null}
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: 48, gap: spacing.md },
});
