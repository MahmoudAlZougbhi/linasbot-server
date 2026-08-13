import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, radii, spacing } from '../../../theme';
import { formatCount, formatRenewDate } from '../dashboardFormat';
import type { TenantDashboard } from '../dashboardTypes';

const CARD_BG = '#0A3D36';
const MINT = '#5EEAD4';
const TRACK = 'rgba(255,255,255,0.18)';

type Plan = TenantDashboard['plan_and_credits'];

type Props = {
  plan: Plan;
  locale: string;
  onBuyCredits: () => void;
  onUpgrade: () => void;
};

export function GrowthPlanCard({ plan, locale, onBuyCredits, onUpgrade }: Props) {
  const { tr } = useI18n();
  if (plan.availability !== 'ok') {
    return (
      <View style={[styles.card, { backgroundColor: CARD_BG }]}>
        <Text style={styles.title}>{tr('dashGrowthPlan')}</Text>
        <Text style={styles.muted}>{plan.message || tr('dashUnavailable')}</Text>
      </View>
    );
  }

  const available = plan.available_credits ?? 0;
  const limit = plan.credits_limit ?? 0;
  const used = plan.credits_consumed_period_estimate ?? Math.max(0, limit - available);
  const ratio =
    typeof plan.usage_progress_ratio === 'number'
      ? Math.max(0, Math.min(1, plan.usage_progress_ratio))
      : 0;
  const renews = formatRenewDate(plan.current_period_end, locale);
  const active = plan.has_subscription || plan.subscription_exempt;
  const displayRatio = limit > 0 ? Math.max(0, Math.min(1, used / limit)) : ratio;

  return (
    <View style={[styles.card, { backgroundColor: CARD_BG }]}>
      <View style={styles.topRow}>
        <View style={styles.planRow}>
          <Text style={styles.title}>{tr('dashGrowthPlan')}</Text>
          {active ? (
            <View style={styles.activePill}>
              <Text style={styles.activeText}>{tr('dashActive')}</Text>
            </View>
          ) : null}
        </View>
        <Pressable onPress={onUpgrade} style={styles.outlineBtn} accessibilityRole="button">
          <Text style={styles.outlineText}>{tr('dashUpgrade')}</Text>
        </Pressable>
      </View>

      <Text style={styles.creditsLabel}>{tr('dashCredits')}</Text>
      <View style={styles.creditsRow}>
        <Text style={styles.creditsBig}>{formatCount(available)}</Text>
        <Text style={styles.remaining}> {tr('dashRemaining')}</Text>
      </View>
      <Text style={styles.usedLine}>
        {formatCount(used)} {tr('dashUsedOf')} {formatCount(limit)}
      </Text>

      <View style={[styles.track, { backgroundColor: TRACK }]}>
        <View style={[styles.fill, { width: `${displayRatio * 100}%`, backgroundColor: MINT }]} />
      </View>

      <View style={styles.bottomRow}>
        <Text style={styles.renews}>
          {renews ? `${tr('dashRenews')} ${renews}` : ''}
        </Text>
        <Pressable onPress={onBuyCredits} style={styles.outlineBtn} accessibilityRole="button">
          <Text style={styles.outlineText}>{tr('dashBuyCredits')}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radii.lg, padding: spacing.lg, gap: spacing.sm },
  topRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.sm },
  planRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, flex: 1, flexWrap: 'wrap' },
  title: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 16 },
  muted: { color: 'rgba(255,255,255,0.75)', fontFamily: fonts.body, fontSize: 13 },
  activePill: {
    backgroundColor: 'rgba(255,255,255,0.16)',
    borderRadius: radii.pill,
    paddingHorizontal: 10,
    paddingVertical: 3,
  },
  activeText: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 12 },
  outlineBtn: {
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.65)',
    borderRadius: radii.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
  },
  outlineText: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 13 },
  creditsLabel: { color: 'rgba(255,255,255,0.75)', fontFamily: fonts.body, fontSize: 13, marginTop: 4 },
  creditsRow: { flexDirection: 'row', alignItems: 'baseline' },
  creditsBig: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 34, fontWeight: '700' },
  remaining: { color: 'rgba(255,255,255,0.7)', fontFamily: fonts.body, fontSize: 14 },
  usedLine: { color: 'rgba(255,255,255,0.75)', fontFamily: fonts.body, fontSize: 13 },
  track: { height: 8, borderRadius: 999, overflow: 'hidden', marginTop: 4 },
  fill: { height: '100%', borderRadius: 999 },
  bottomRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: spacing.sm },
  renews: { color: 'rgba(255,255,255,0.75)', fontFamily: fonts.body, fontSize: 13, flex: 1 },
});
