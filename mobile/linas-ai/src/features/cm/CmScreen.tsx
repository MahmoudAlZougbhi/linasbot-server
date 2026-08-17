import { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text } from 'react-native';

import { ApiError } from '../../api/client';
import { EmptyState } from '../../components/EmptyState';
import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
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

/** CM overview — design handoff layout with live progress + section grid. */
export function CmScreen({ onOpenSection, onOpenProducts, onContinueSetup }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const [loading, setLoading] = useState(true);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<CmMeta | null>(null);
  const [rows, setRows] = useState<CmProgressRow[]>([]);
  const [productsComplete, setProductsComplete] = useState(false);
  const [live, setLive] = useState(false);
  const [liveBusy, setLiveBusy] = useState(false);
  const [filter, setFilter] = useState<AiSetupFilter>('all');

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [metaRes, prog, productsRes] = await Promise.all([
        fetchCmMeta(),
        fetchCmSetupProgress(),
        fetchProducts().catch(() => ({ products: [], total: 0 })),
      ]);
      setMeta(metaRes);
      const progressRows = prog.progress ?? [];
      setRows(progressRows);
      setProductsComplete((productsRes.total ?? productsRes.products.length) > 0);
      setLive(Boolean(prog.summary?.published ?? metaRes.has_published_content));
      setHydrated(true);
      setError(null);
    } catch {
      setError(tr('aiSetupLoadError'));
    } finally {
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
          detail.trim() || tr('aiSetupLiveToggleFailedBody'),
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
      {loading && !hasLoadedOnce ? <LinasLoadingIndicator variant="screen" style={styles.loader} /> : null}
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
  loader: { marginVertical: spacing.sm },
});
