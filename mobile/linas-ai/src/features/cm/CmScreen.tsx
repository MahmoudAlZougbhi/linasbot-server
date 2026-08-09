import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { EmptyState } from '../../components/EmptyState';
import { StatusChip } from '../../components/StatusChip';
import { colors, fonts, radii, spacing } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import { fetchCmMeta, type CmMeta } from './cmApi';
import { CM_HUB_CARDS, getCmSection, type CmSectionId } from './cmSections';

type Props = {
  onBack: () => void;
  onOpenSection: (section: CmSectionId) => void;
};

export function CmScreen({ onBack, onOpenSection }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<CmMeta | null>(null);

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
    return CM_HUB_CARDS.filter((card) => apiSections.size === 0 || apiSections.has(card.id));
  }, [meta]);

  return (
    <ScreenChrome
      title="Content Management"
      subtitle="Tap a section to edit its live CM draft"
      onBack={onBack}
    >
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <ScrollView contentContainerStyle={styles.list}>
        {meta ? (
          <View style={styles.card}>
            <View style={styles.head}>
              <Text style={styles.cardTitle}>Runtime</Text>
              <StatusChip
                label={meta.tenant_runtime ?? meta.runtime_mode ?? 'unknown'}
                tone={meta.has_published_content ? 'ok' : 'warn'}
              />
            </View>
            <Text style={styles.line}>
              Publish: {meta.publish_enabled ? 'enabled' : 'disabled / gated'}
            </Text>
            <Text style={styles.line}>
              Published content: {meta.has_published_content ? 'yes' : 'no'}
            </Text>
          </View>
        ) : null}

        <Text style={styles.gridLabel}>Sections</Text>
        <View style={styles.grid}>
          {tiles.map((tile) => {
            const known = getCmSection(tile.id);
            const supported = known?.mobileSupported !== false;
            return (
              <Pressable
                key={tile.id}
                style={[styles.tile, !supported && styles.tileDisabled]}
                disabled={!supported}
                onPress={() => {
                  if (supported) onOpenSection(tile.id);
                }}
              >
                <Text style={styles.tileTitle}>{tile.title}</Text>
                <Text style={styles.tileSub}>{tile.description}</Text>
              </Pressable>
            );
          })}
        </View>

        {!loading && !meta && !error ? (
          <EmptyState title="CM unavailable" body="Retry after API deploy." />
        ) : null}
      </ScrollView>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: 40, gap: spacing.md },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  cardTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 16 },
  line: { color: colors.textMuted, fontFamily: fonts.body, marginTop: 4 },
  gridLabel: {
    color: colors.textDim,
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  tile: {
    width: '47%',
    minHeight: 96,
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    justifyContent: 'center',
  },
  tileDisabled: { opacity: 0.55 },
  tileTitle: { color: colors.accentDeep, fontFamily: fonts.bodyMedium, fontSize: 14 },
  tileSub: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 11, marginTop: 4 },
  error: { color: colors.danger, marginBottom: spacing.md, fontFamily: fonts.body },
});
