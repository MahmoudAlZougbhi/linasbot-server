import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { EmptyState } from '../../components/EmptyState';
import { HIT, fonts, radii, spacing, useTheme } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import { CmReadinessCard } from './CmReadinessCard';
import { fetchCmMeta, type CmMeta } from './cmApi';
import {
  buildFillMissingPrompt,
  fetchCmSetupProgress,
  type CmProgressRow,
} from './cmProgressApi';
import { CM_SECTION_ICONS } from './cmSectionIcons';
import { CM_HUB_CARDS, CM_SECTION_CARDS, type CmSectionId } from './cmSections';

type Props = {
  onOpenSection: (section: CmSectionId) => void;
  onContinueSetup?: (prompt: string) => void;
};

function titleMap(): Record<string, string> {
  return Object.fromEntries(CM_SECTION_CARDS.map((c) => [c.id, c.title]));
}

/** CM overview — real fill progress + section rows with Filled / Missing. */
export function CmScreen({ onOpenSection, onContinueSetup }: Props) {
  const { colors } = useTheme();
  const [loading, setLoading] = useState(true);
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
  const [query, setQuery] = useState('');
  const [issuesOnly, setIssuesOnly] = useState(false);

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
      setError(null);
    } catch {
      setError('Could not load AI Setup progress.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const statusBySection = useMemo(() => {
    const map = new Map<string, 'complete' | 'incomplete'>();
    for (const row of rows) map.set(row.section, row.status);
    return map;
  }, [rows]);

  const tiles = useMemo(() => {
    const apiSections = new Set((meta?.sections ?? []).map((s) => s.replace(/-/g, '_')));
    const base =
      apiSections.size === 0
        ? CM_HUB_CARDS
        : CM_HUB_CARDS.filter((card) => apiSections.has(card.id));
    const q = query.trim().toLowerCase();
    return base.filter((t) => {
      if (q && !`${t.title} ${t.description}`.toLowerCase().includes(q)) return false;
      if (issuesOnly) {
        const st = statusBySection.get(t.id);
        if (st === 'complete') return false;
      }
      return true;
    });
  }, [meta, query, issuesOnly, statusBySection]);

  const titles = useMemo(() => titleMap(), []);
  const missingPreview = useMemo(
    () => summary.missing_sections.map((id) => titles[id] || id.replace(/_/g, ' ')),
    [summary.missing_sections, titles],
  );
  const ctaLabel =
    summary.incomplete > 0 ? 'Fill missing with Linas AI' : 'Review setup with Linas AI';

  return (
    <ScreenChrome
      title="AI Setup"
      subtitle="Configure the AI that answers customer DMs and comments"
     
    >
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={{ color: colors.danger }}>{error}</Text> : null}
      <ScrollView contentContainerStyle={styles.list}>
        <CmReadinessCard
          percent={summary.percent}
          complete={summary.complete}
          total={summary.total}
          published={summary.published}
          missingPreview={missingPreview}
          ctaLabel={ctaLabel}
          onContinueSetup={
            onContinueSetup
              ? () => onContinueSetup(buildFillMissingPrompt(summary.missing_sections, titles))
              : undefined
          }
        />

        <View style={[styles.searchWrap, { backgroundColor: colors.input, borderColor: colors.border }]}>
          <AppIcon icon={feather('search')} size={16} color={colors.textDim} />
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder="Search sections"
            placeholderTextColor={colors.textDim}
            style={[styles.search, { color: colors.text }]}
            accessibilityLabel="Search AI Setup sections"
          />
        </View>

        <Pressable
          onPress={() => setIssuesOnly((v) => !v)}
          style={styles.issueToggle}
          accessibilityRole="button"
          accessibilityLabel={issuesOnly ? 'Show all sections' : 'Show missing sections only'}
        >
          <Text style={{ color: colors.accent }}>
            {issuesOnly ? 'Show all sections' : 'Show missing only'}
          </Text>
        </Pressable>

        <Text style={[styles.gridLabel, { color: colors.textDim }]}>Configuration</Text>
        <View style={[styles.rows, { borderColor: colors.border, backgroundColor: colors.surface }]}>
          {tiles.map((tile, index) => {
            const supported = tile.mobileSupported !== false;
            const fill = statusBySection.get(tile.id);
            const statusLabel = !supported
              ? tile.disabledReason || 'Unavailable'
              : fill === 'complete'
                ? 'Filled'
                : 'Missing';
            const statusColor =
              fill === 'complete' ? colors.mint : fill === 'incomplete' ? colors.warning : colors.textDim;
            return (
              <Pressable
                key={tile.id}
                style={[
                  styles.row,
                  index < tiles.length - 1 && {
                    borderBottomWidth: StyleSheet.hairlineWidth,
                    borderBottomColor: colors.border,
                  },
                  { opacity: supported ? 1 : 0.55 },
                ]}
                disabled={!supported}
                onPress={() => supported && onOpenSection(tile.id)}
                accessibilityRole="button"
                accessibilityLabel={`${tile.title}, ${statusLabel}`}
                accessibilityState={{ disabled: !supported }}
              >
                <View style={[styles.rowIcon, { backgroundColor: colors.accentSoft }]}>
                  <AppIcon icon={CM_SECTION_ICONS[tile.id]} size={18} color={colors.accentDeep} />
                </View>
                <View style={styles.rowBody}>
                  <Text style={{ color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 15 }}>
                    {tile.title}
                  </Text>
                  <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 2 }} numberOfLines={1}>
                    {supported ? tile.description : tile.disabledReason || tile.description}
                  </Text>
                </View>
                <Text style={{ color: statusColor, fontSize: 12, marginRight: 4, fontFamily: fonts.bodyMedium }}>
                  {statusLabel}
                </Text>
                <AppIcon icon={feather('chevron-right')} size={18} color={colors.textDim} />
              </Pressable>
            );
          })}
        </View>

        {summary.published ? null : (
          <View style={[styles.sticky, { backgroundColor: colors.accent }]}>
            <Text style={{ color: colors.onAccent, fontFamily: fonts.bodyMedium, textAlign: 'center' }}>
              Review & publish when ready
            </Text>
          </View>
        )}

        {!loading && !meta && !error ? (
          <EmptyState
            title="AI Setup unavailable"
            body="Something went wrong. Please try again."
          />
        ) : null}
      </ScrollView>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: 48, gap: spacing.md },
  searchWrap: {
    minHeight: HIT,
    borderRadius: radii.md,
    borderWidth: 1,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  search: { flex: 1, minHeight: HIT - 4, paddingVertical: 8 },
  issueToggle: { minHeight: 44, justifyContent: 'center' },
  gridLabel: {
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  rows: { borderRadius: radii.lg, borderWidth: 1, overflow: 'hidden' },
  row: {
    minHeight: HIT + 8,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    gap: 10,
  },
  rowIcon: {
    width: 36,
    height: 36,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowBody: { flex: 1, minWidth: 0 },
  sticky: {
    marginTop: spacing.md,
    minHeight: 52,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 12,
  },
});
