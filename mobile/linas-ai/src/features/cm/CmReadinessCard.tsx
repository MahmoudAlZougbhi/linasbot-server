import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { StatusChip } from '../../components/StatusChip';
import { HIT, fonts, radii, spacing, useTheme } from '../../theme';

type Props = {
  percent: number;
  complete: number;
  total: number;
  published: boolean;
  missingPreview: string[];
  onContinueSetup?: () => void;
  ctaLabel: string;
};

/** Compact readiness card: real fill % + CTA into Owner Copilot. */
export function CmReadinessCard({
  percent,
  complete,
  total,
  published,
  missingPreview,
  onContinueSetup,
  ctaLabel,
}: Props) {
  const { colors } = useTheme();
  const lifecycle = published ? 'Published / Live' : complete > 0 ? 'Draft' : 'Not started';
  const missingLine =
    missingPreview.length === 0
      ? 'All tracked sections have content.'
      : `Still missing: ${missingPreview.slice(0, 4).join(', ')}${
          missingPreview.length > 4 ? ` +${missingPreview.length - 4}` : ''
        }`;

  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <View style={styles.head}>
        <View style={styles.headLeft}>
          <AppIcon icon={feather('check-circle')} size={18} color={colors.accent} />
          <Text style={[styles.cardTitle, { color: colors.text }]}>Setup progress</Text>
        </View>
        <StatusChip label={lifecycle} tone={published ? 'ok' : 'warn'} />
      </View>
      <Text style={{ color: colors.textMuted, marginTop: 6 }}>
        {complete}/{total} sections filled · {percent}%
      </Text>
      <View style={styles.progressTrack}>
        <View
          style={[
            styles.progressFill,
            { backgroundColor: colors.progressFill, width: `${Math.min(100, percent)}%` },
          ]}
        />
      </View>
      <Text style={{ color: colors.textDim, fontSize: 12, marginTop: 8 }}>{missingLine}</Text>
      {onContinueSetup ? (
        <Pressable
          style={[styles.setupBtn, { backgroundColor: colors.accentSoft, borderColor: colors.accent }]}
          onPress={onContinueSetup}
          accessibilityRole="button"
          accessibilityLabel={ctaLabel}
        >
          <AppIcon icon={feather('star')} size={18} color={colors.accentDeep} />
          <Text style={{ color: colors.accentDeep, fontFamily: fonts.bodyMedium }}>{ctaLabel}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radii.lg, padding: spacing.lg, borderWidth: 1, gap: 4 },
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  headLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  cardTitle: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  progressTrack: {
    height: 8,
    borderRadius: 4,
    backgroundColor: '#D7E5E3',
    marginTop: 8,
    overflow: 'hidden',
  },
  progressFill: { height: 8 },
  setupBtn: {
    minHeight: HIT,
    marginTop: spacing.sm,
    borderRadius: radii.md,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
  },
});
