import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, radii, spacing, useTheme } from '../../../theme';
import type { TenantDashboard } from '../dashboardTypes';

type Content = TenantDashboard['content_readiness'];

type Props = {
  content: Content;
  onOpenCm: () => void;
  onReviewFaq: () => void;
};

export function ContentReadinessCard({ content, onOpenCm, onReviewFaq }: Props) {
  const { colors } = useTheme();
  if (content.availability === 'error') {
    return (
      <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Text style={[styles.title, { color: colors.text }]}>Content readiness</Text>
        <Text style={{ color: colors.danger, fontFamily: fonts.body }}>
          {content.message || 'Content Management progress unavailable'}
        </Text>
      </View>
    );
  }

  const pct = content.percent ?? 0;
  const missing = content.missing_sections ?? [];

  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <Text style={[styles.title, { color: colors.text }]}>Content readiness</Text>
      <Text style={{ color: colors.textMuted, fontFamily: fonts.body }}>
        {content.published ? 'Published' : 'Draft'} · {pct}% complete
        {content.sections_present != null && content.sections_total != null
          ? ` · ${content.sections_present}/${content.sections_total} sections`
          : ''}
      </Text>
      <View style={[styles.track, { backgroundColor: colors.progressTrack }]}>
        <View
          style={[styles.fill, { width: `${Math.max(0, Math.min(100, pct))}%`, backgroundColor: colors.progressFill }]}
        />
      </View>
      {content.last_published_at ? (
        <Text style={{ color: colors.textDim, fontFamily: fonts.body, fontSize: 12 }}>
          Last published {new Date(content.last_published_at).toLocaleString()}
        </Text>
      ) : (
        <Text style={{ color: colors.textDim, fontFamily: fonts.body, fontSize: 12 }}>
          Not published yet
        </Text>
      )}
      <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 }}>
        FAQ: {content.faq_quota_display || 'Unavailable'}
      </Text>
      <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 }}>
        Off days: {content.off_days_status || 'unknown'}
      </Text>
      {missing.length > 0 ? (
        <Text style={{ color: colors.textDim, fontFamily: fonts.body, fontSize: 12 }}>
          Still needed: {missing.slice(0, 6).join(', ')}
          {missing.length > 6 ? ` (+${missing.length - 6})` : ''}
        </Text>
      ) : null}
      <View style={styles.actions}>
        <Pressable onPress={onOpenCm} accessibilityRole="button">
          <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>
            {content.published ? 'Open Content Management' : 'Continue setup'}
          </Text>
        </Pressable>
        <Pressable onPress={onReviewFaq} accessibilityRole="button">
          <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>Review FAQ</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radii.lg, borderWidth: 1, padding: spacing.lg, gap: spacing.sm },
  title: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  track: { height: 8, borderRadius: 999, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 999 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md, marginTop: 4 },
});
