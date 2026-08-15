import { useCallback, useEffect, useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text } from 'react-native';

import { EmptyState } from '../../components/EmptyState';
import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import { useI18n } from '../../i18n/LanguageContext';
import { spacing, useTheme } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import { AiSetupFilterTabs, type AiSetupFilter } from './AiSetupFilterTabs';
import { AiSetupProductsCard } from '../products/AiSetupProductsCard';
import { AiSetupProgressCard } from './AiSetupProgressCard';
import { AiSetupSectionGrid } from './AiSetupSectionGrid';
import { fetchCmMeta, type CmMeta } from './cmApi';
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
  const [summary, setSummary] = useState({
    complete: 0,
    incomplete: 0,
    total: 0,
    percent: 0,
    published: false,
    missing_sections: [] as string[],
  });
  const [filter, setFilter] = useState<AiSetupFilter>('all');

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [metaRes, prog] = await Promise.all([fetchCmMeta(), fetchCmSetupProgress()]);
      setMeta(metaRes);
      const progressRows = prog.progress ?? [];
      setRows(progressRows);
      const s = prog.summary;
      if (s) {
        setSummary({
          complete: s.complete,
          incomplete: s.incomplete,
          total: s.total,
          percent: s.percent,
          published: Boolean(s.published ?? metaRes.has_published_content),
          missing_sections: s.missing_sections ?? [],
        });
      } else {
        const complete = progressRows.filter((r) => r.status === 'complete').length;
        const total = progressRows.length || 1;
        setSummary({
          complete,
          incomplete: total - complete,
          total,
          percent: Math.round((complete / total) * 100),
          published: Boolean(metaRes.has_published_content),
          missing_sections: progressRows.filter((r) => r.status !== 'complete').map((r) => r.section),
        });
      }
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

  const displaySummary = useMemo(() => summarizeHubProgress(rows), [rows]);

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

  /** Products hub card sits where Knowledge used to be — after Prices, before Comments. */
  const { tilesBeforeProducts, tilesAfterProducts } = useMemo(() => {
    const splitAt = tiles.findIndex((tile) => tile.id === 'comments');
    if (splitAt === -1) {
      return { tilesBeforeProducts: tiles, tilesAfterProducts: [] as typeof tiles };
    }
    return {
      tilesBeforeProducts: tiles.slice(0, splitAt),
      tilesAfterProducts: tiles.slice(splitAt),
    };
  }, [tiles]);

  const titleMap = useMemo(
    () => Object.fromEntries(CM_HUB_CARDS.map((c) => [c.id, tr(cmSectionTitleKey(c.id))])),
    [tr],
  );

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
            published={summary.published}
            incomplete={displaySummary.incomplete}
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

          <AiSetupSectionGrid
            tiles={tilesBeforeProducts}
            statusBySection={statusBySection}
            onOpenSection={onOpenSection}
          />

          {onOpenProducts ? <AiSetupProductsCard onOpenProducts={onOpenProducts} /> : null}

          {tilesAfterProducts.length > 0 ? (
            <AiSetupSectionGrid
              tiles={tilesAfterProducts}
              statusBySection={statusBySection}
              onOpenSection={onOpenSection}
            />
          ) : null}

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
