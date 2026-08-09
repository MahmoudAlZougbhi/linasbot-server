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

import { EmptyState } from '../../components/EmptyState';
import { StatusChip } from '../../components/StatusChip';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import { fetchCmMeta, type CmMeta } from './cmApi';
import { CM_SECTION_CARDS, getCmSection, type CmSectionId } from './cmSections';

type Props = {
  onBack: () => void;
  onOpenSection: (section: CmSectionId) => void;
  onContinueSetup?: () => void;
};

/** CM-01 overview — PDF layout + Draft / Valid / Published lifecycle (V2). */
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
    const apiSections = (meta?.sections ?? []).map((s) => s.replace(/-/g, '_'));
    const base =
      apiSections.length === 0
        ? CM_SECTION_CARDS
        : apiSections.map((id) => {
            const known = getCmSection(id);
            if (known) return known;
            return {
              id: id as CmSectionId,
              title: id.replace(/_/g, ' '),
              description: 'Backend section',
              mobileSupported: false,
              disabledReason: 'No mobile editor for this section yet.',
            };
          });
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
            <Text style={[styles.cardTitle, { color: colors.text }]}>Readiness</Text>
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
          accessibilityLabel="Continue setup with Linas AI"
        >
          <Text style={{ color: colors.accentDeep, fontFamily: fonts.bodyMedium }}>
            Continue setup with Linas AI
          </Text>
        </Pressable>

        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="Search sections"
          placeholderTextColor={colors.textDim}
          style={[
            styles.search,
            { backgroundColor: colors.input, borderColor: colors.border, color: colors.text },
          ]}
          accessibilityLabel="Search Content Management sections"
        />

        <Pressable onPress={() => setIssuesOnly((v) => !v)}>
          <Text style={{ color: colors.accent, marginBottom: 8 }}>
            {issuesOnly ? 'Show all sections' : 'View unsupported / issue rows'}
          </Text>
        </Pressable>

        <Text style={[styles.gridLabel, { color: colors.textDim }]}>Configuration</Text>
        <View style={styles.grid}>
          {tiles.map((tile) => {
            const supported = tile.mobileSupported !== false;
            const title =
              tile.id === 'faq' || tile.title.toLowerCase().includes('smart')
                ? tile.title.replace(/Smart Answers/gi, 'Answers').replace(/FAQ & Smart Answers/gi, 'FAQ')
                : tile.title;
            return (
              <Pressable
                key={tile.id}
                style={[
                  styles.tile,
                  {
                    backgroundColor: colors.surface,
                    borderColor: colors.border,
                    opacity: supported ? 1 : 0.55,
                  },
                ]}
                disabled={!supported}
                onPress={() => supported && onOpenSection(tile.id)}
                accessibilityLabel={title}
              >
                <Text style={{ color: colors.accentDeep, fontFamily: fonts.bodyMedium, fontSize: 14 }}>
                  {title}
                </Text>
                <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>
                  {supported ? tile.description : tile.disabledReason || tile.description}
                </Text>
                <Text style={{ color: colors.textDim, fontSize: 11, marginTop: 6 }}>
                  {published ? 'Live source' : 'Draft editor'}
                </Text>
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
    minHeight: 48,
    borderRadius: radii.md,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  search: {
    minHeight: 48,
    borderRadius: radii.md,
    borderWidth: 1,
    paddingHorizontal: 12,
  },
  gridLabel: {
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  tile: {
    width: '47%',
    minHeight: 96,
    borderRadius: radii.lg,
    padding: spacing.md,
    borderWidth: 1,
    justifyContent: 'center',
  },
  sticky: {
    marginTop: spacing.md,
    minHeight: 52,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 12,
  },
});
