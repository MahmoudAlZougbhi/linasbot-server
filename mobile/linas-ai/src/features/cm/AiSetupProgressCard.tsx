import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather, ion } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { HIT, fonts, radii, spacing } from '../../theme';
import {
  AI_SETUP_CARD_BORDER,
  AI_SETUP_ORANGE,
  AI_SETUP_PROGRESS_TRACK,
  AI_SETUP_TEAL,
  AI_SETUP_TEAL_SOFT,
} from './aiSetupDesign';

type Props = {
  percent: number;
  complete: number;
  total: number;
  published: boolean;
  incomplete: number;
  onContinueSetup?: () => void;
};

/** Setup progress card — real fill %, Live badge, attention line, Linas CTA. */
export function AiSetupProgressCard({
  percent,
  complete,
  total,
  published,
  incomplete,
  onContinueSetup,
}: Props) {
  const { tr } = useI18n();
  const pct = Math.min(100, Math.max(0, Math.round(percent)));
  const attentionLine =
    incomplete > 0
      ? tr('aiSetupNeedAttention').replace('{count}', String(incomplete))
      : tr('aiSetupAllComplete');

  return (
    <View style={[styles.card, { borderColor: AI_SETUP_CARD_BORDER }]}>
      <View style={styles.head}>
        <View style={styles.headLeft}>
          <View style={styles.checkCircle}>
            <AppIcon icon={feather('check')} size={12} color="#FFFFFF" />
          </View>
          <Text style={styles.progressLabel}>{tr('aiSetupProgressLabel')}</Text>
        </View>
        <View style={[styles.liveBadge, { backgroundColor: published ? AI_SETUP_TEAL : AI_SETUP_TEAL_SOFT }]}>
          <Text style={[styles.liveText, { color: published ? '#FFFFFF' : AI_SETUP_TEAL }]}>
            {published ? tr('aiSetupLive') : tr('aiSetupDraft')}
          </Text>
        </View>
      </View>

      <Text style={styles.percentLine}>{tr('aiSetupPercentComplete').replace('{percent}', String(pct))}</Text>
      <Text style={styles.subLine}>
        {tr('aiSetupSectionsOf').replace('{complete}', String(complete)).replace('{total}', String(total))}
      </Text>

      <View style={[styles.track, { backgroundColor: AI_SETUP_PROGRESS_TRACK }]}>
        <View style={[styles.fill, { width: `${pct}%`, backgroundColor: AI_SETUP_TEAL }]} />
      </View>

      <View style={styles.footer}>
        <View style={styles.attentionRow}>
          {incomplete > 0 ? <View style={styles.orangeDot} /> : null}
          <Text style={[styles.attentionText, { color: incomplete > 0 ? AI_SETUP_ORANGE : '#8A9A98' }]}>
            {attentionLine}
          </Text>
        </View>
        {onContinueSetup ? (
          <Pressable
            style={[styles.ctaBtn, { borderColor: AI_SETUP_TEAL }]}
            onPress={onContinueSetup}
            accessibilityRole="button"
            accessibilityLabel={tr('aiSetupCompleteWithLinas')}
          >
            <AppIcon icon={ion('sparkles-outline')} size={16} color={AI_SETUP_TEAL} />
            <Text style={[styles.ctaText, { color: AI_SETUP_TEAL }]}>{tr('aiSetupCompleteWithLinas')}</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: radii.lg,
    borderWidth: 1,
    padding: spacing.lg,
    gap: 6,
  },
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  headLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  checkCircle: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: AI_SETUP_TEAL,
    alignItems: 'center',
    justifyContent: 'center',
  },
  progressLabel: { fontFamily: fonts.bodyMedium, fontSize: 15, color: '#10221A' },
  liveBadge: {
    borderRadius: radii.pill,
    paddingHorizontal: 12,
    paddingVertical: 4,
  },
  liveText: { fontFamily: fonts.bodyMedium, fontSize: 12 },
  percentLine: {
    fontFamily: fonts.display,
    fontSize: 28,
    color: '#10221A',
    marginTop: 4,
  },
  subLine: { fontFamily: fonts.body, fontSize: 14, color: '#8A9A98', marginBottom: 4 },
  track: { height: 8, borderRadius: 4, overflow: 'hidden' },
  fill: { height: 8, borderRadius: 4 },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 10,
    gap: 10,
  },
  attentionRow: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6, minWidth: 0 },
  orangeDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: AI_SETUP_ORANGE },
  attentionText: { fontFamily: fonts.bodyMedium, fontSize: 13, flexShrink: 1 },
  ctaBtn: {
    minHeight: HIT - 8,
    borderRadius: radii.pill,
    borderWidth: 1.5,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: '#FFFFFF',
  },
  ctaText: { fontFamily: fonts.bodyMedium, fontSize: 13 },
});
