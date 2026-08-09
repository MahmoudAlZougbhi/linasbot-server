import { useEffect, useMemo, useState } from 'react';
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
import { StatusChip } from '../../components/StatusChip';
import { HIT, fonts, radii, spacing, useTheme } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import { fetchCmMeta, type CmMeta } from './cmApi';
import { CM_SECTION_ICONS } from './cmSectionIcons';
import { CM_HUB_CARDS, type CmSectionId } from './cmSections';

type Props = {
  onBack: () => void;
  onOpenSection: (section: CmSectionId) => void;
  onContinueSetup?: () => void;
};

/** CM-01 overview — PDF list rows with section icons + Draft / Valid / Published lifecycle. */
export function CmScreen({ onBack, onOpenSection, onContinueSetup }: Props) {
  const { colors } = useTheme();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<CmMeta | null>(null);
  const [query, setQuery] = useState('');
  const [issuesOnly, setIssuesOnly] = useState(false);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        setMeta(await fetchCmMeta());
        setError(null);
      } catch {
        setError('Could not load Content Management meta.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const tiles = useMemo(() => {
    const apiSections = new Set((meta?.sections ?? []).map((s) => s.replace(/-/g, '_')));
    // Hub shows only mobile CM sections — never Actions/AI Limits/FAQ/web hubs.
    const base =
      apiSections.size === 0
        ? CM_HUB_CARDS
        : CM_HUB_CARDS.filter((card) => apiSections.has(card.id));
    const q = query.trim().toLowerCase();
    return base.filter((t) => {
      if (q && !`${t.title} ${t.description}`.toLowerCase().includes(q)) return false;
      if (issuesOnly && t.mobileSupported !== false) return false;
      return true;
    });
  }, [meta, query, issuesOnly]);

  const published = Boolean(meta?.has_published_content);
  const lifecycle = published ? 'Published / Live' : meta ? 'Draft' : 'Unknown';
  const readyCount = tiles.filter((t) => t.mobileSupported !== false).length;

  return (
    <ScreenChrome
      title="Content Management"
      subtitle="Configure the AI that answers DMs and comments — not social publishing"
      onBack={onBack}
    >
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={{ color: colors.danger }}>{error}</Text> : null}
      <ScrollView contentContainerStyle={styles.list}>
        <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <View style={styles.head}>
            <View style={styles.headLeft}>
              <AppIcon icon={feather('check-circle')} size={18} color={colors.accent} />
              <Text style={[styles.cardTitle, { color: colors.text }]}>Readiness</Text>
            </View>
            <StatusChip label={lifecycle} tone={published ? 'ok' : 'warn'} />
          </View>
          <Text style={{ color: colors.textMuted, marginTop: 6 }}>
            {readyCount} configuration sections reachable on mobile
            {meta?.publish_enabled ? ' · publish enabled' : ' · publish gated'}
          </Text>
          <View style={styles.progressTrack}>
            <View
              style={[
                styles.progressFill,
                {
                  backgroundColor: colors.progressFill,
                  width: `${Math.min(100, Math.round((readyCount / Math.max(tiles.length, 1)) * 100))}%`,
                },
              ]}
            />
          </View>
          <Text style={{ color: colors.textDim, fontSize: 12, marginTop: 8 }}>
            Lifecycle: Draft → Review → Valid → Published / Live
          </Text>
        </View>

        <Pressable
          style={[styles.setupBtn, { backgroundColor: colors.accentSoft, borderColor: colors.accent }]}
          onPress={onContinueSetup}
          accessibilityRole="button"
          accessibilityLabel="Continue setup with Linas AI"
        >
          <AppIcon icon={feather('star')} size={18} color={colors.accentDeep} />
          <Text style={{ color: colors.accentDeep, fontFamily: fonts.bodyMedium }}>
            Continue setup with Linas AI
          </Text>
        </Pressable>

        <View style={[styles.searchWrap, { backgroundColor: colors.input, borderColor: colors.border }]}>
          <AppIcon icon={feather('search')} size={16} color={colors.textDim} />
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder="Search sections"
            placeholderTextColor={colors.textDim}
            style={[styles.search, { color: colors.text }]}
            accessibilityLabel="Search Content Management sections"
          />
        </View>

        <Pressable
          onPress={() => setIssuesOnly((v) => !v)}
          style={styles.issueToggle}
          accessibilityRole="button"
          accessibilityLabel={issuesOnly ? 'Show all sections' : 'View unsupported or issue rows'}
        >
          <Text style={{ color: colors.accent }}>
            {issuesOnly ? 'Show all sections' : 'View unsupported / issue rows'}
          </Text>
        </Pressable>

        <Text style={[styles.gridLabel, { color: colors.textDim }]}>Configuration</Text>
        <View style={[styles.rows, { borderColor: colors.border, backgroundColor: colors.surface }]}>
          {tiles.map((tile, index) => {
            const supported = tile.mobileSupported !== false;
            const statusLabel = supported
              ? published
                ? 'Live'
                : 'Draft'
              : tile.disabledReason || 'Unavailable';
            return (
              <Pressable
                key={tile.id}
                style={[
                  styles.row,
                  index < tiles.length - 1 && { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
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
                <Text style={{ color: colors.textDim, fontSize: 12, marginRight: 4 }}>{statusLabel}</Text>
                <AppIcon icon={feather('chevron-right')} size={18} color={colors.textDim} />
              </Pressable>
            );
          })}
        </View>

        {published ? null : (
          <View style={[styles.sticky, { backgroundColor: colors.accent }]}>
            <Text style={{ color: colors.onAccent, fontFamily: fonts.bodyMedium, textAlign: 'center' }}>
              Review & Publish (explicit confirmation in chat / CM publish flow)
            </Text>
          </View>
        )}

        {!loading && !meta && !error ? (
          <EmptyState title="CM unavailable" body="Retry after API deploy." />
        ) : null}
      </ScrollView>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: 48, gap: spacing.md },
  card: { borderRadius: radii.lg, padding: spacing.lg, borderWidth: 1 },
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  headLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  cardTitle: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  progressTrack: {
    height: 8,
    borderRadius: 4,
    backgroundColor: '#D7E5E3',
    marginTop: 12,
    overflow: 'hidden',
  },
  progressFill: { height: 8 },
  setupBtn: {
    minHeight: HIT,
    borderRadius: radii.md,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
  },
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
  rows: {
    borderRadius: radii.lg,
    borderWidth: 1,
    overflow: 'hidden',
  },
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
