import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../../theme';
import {
  DASH_BAR_HEIGHT,
  DASH_BTN_RADIUS,
  DASH_CARD_RADIUS,
  DASH_FOREST,
  DASH_MINT,
  DASH_MINT_SOFT,
  DASH_TRACK,
} from '../dashboardChrome';
import { isHighestPlan, isPlanId } from '../../billing/planCatalog';
import { planNameColor } from '../../billing/planColors';
import { formatCount, formatRenewDate } from '../dashboardFormat';
import type { TenantDashboard } from '../dashboardTypes';

type Plan = TenantDashboard['plan_and_credits'];

type Props = {
  plan: Plan;
  locale: string;
  onBuyCredits: () => void;
  onUpgrade: () => void;
};

export function GrowthPlanCard({ plan, locale, onBuyCredits, onUpgrade }: Props) {
  const { tr } = useI18n();
  const { resolved } = useTheme();
  const planName = (plan.plan_name || plan.plan_id || '').trim();
  const planId = isPlanId(plan.plan_id) ? plan.plan_id : null;
  const planNameTint = planId ? planNameColor(planId, resolved) : DASH_MINT;

  if (plan.availability !== 'ok') {
    const fallbackTitle = planName
      ? tr('dashPlanTitle').replace('{name}', planName)
      : tr('dashNoPlan');
    return (
      <View style={styles.card}>
        <Text style={styles.title}>{fallbackTitle}</Text>
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
  const showUpgrade = !isHighestPlan(plan.plan_id);

  return (
    <View style={styles.card}>
      <View style={styles.topRow}>
        <View style={styles.planRow}>
          <Text style={styles.title}>
            {planName
              ? renderPlanTitle(tr('dashPlanTitle'), planName, planNameTint)
              : tr('dashNoPlan')}
          </Text>
          {active ? (
            <View style={styles.activePill}>
              <Text style={styles.activeText}>{tr('dashActive')}</Text>
            </View>
          ) : null}
        </View>
        {showUpgrade ? (
          <Pressable onPress={onUpgrade} style={styles.outlineBtn} accessibilityRole="button">
            <Text style={styles.outlineText}>{tr('dashUpgrade')}</Text>
          </Pressable>
        ) : null}
      </View>
      <View style={styles.headerRule} />

      <Text style={styles.creditsLabel}>{tr('dashCredits')}</Text>
      <View style={styles.creditsRow}>
        <Text style={styles.creditsBig}>{formatCount(available)}</Text>
        <Text style={styles.remaining}> {tr('dashRemaining')}</Text>
      </View>
      <Text style={styles.usedLine}>
        {formatCount(used)} {tr('dashUsedOf')} {formatCount(limit)}
      </Text>

      <View style={styles.track}>
        <View style={[styles.fill, { width: `${displayRatio * 100}%` }]} />
      </View>

      <View style={styles.bottomRow}>
        <Text style={styles.renews}>{renews ? `${tr('dashRenews')} ${renews}` : ''}</Text>
        <Pressable onPress={onBuyCredits} style={styles.buyBtn} accessibilityRole="button">
          <Text style={styles.buyText}>{tr('dashBuyCredits')}</Text>
        </Pressable>
      </View>
    </View>
  );
}

function renderPlanTitle(template: string, planName: string, nameColor: string) {
  const marker = '{name}';
  const idx = template.indexOf(marker);
  if (idx === -1 || !planName) {
    return template.replace(marker, planName);
  }
  const before = template.slice(0, idx);
  const after = template.slice(idx + marker.length);
  return (
    <>
      {before}
      <Text style={{ color: nameColor }}>{planName}</Text>
      {after}
    </>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: DASH_FOREST,
    borderRadius: DASH_CARD_RADIUS,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  topRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.sm },
  planRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, flex: 1, flexWrap: 'wrap' },
  title: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  muted: { color: 'rgba(255,255,255,0.75)', fontFamily: fonts.body, fontSize: 13 },
  activePill: {
    backgroundColor: DASH_MINT_SOFT,
    borderRadius: DASH_BTN_RADIUS,
    paddingHorizontal: 10,
    paddingVertical: 3,
  },
  activeText: { color: DASH_FOREST, fontFamily: fonts.bodyMedium, fontSize: 12, fontWeight: '600' },
  outlineBtn: {
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.85)',
    borderRadius: DASH_BTN_RADIUS,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
  },
  outlineText: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 13 },
  headerRule: { height: 1, backgroundColor: DASH_TRACK, marginVertical: 4 },
  creditsLabel: { color: DASH_MINT_SOFT, fontFamily: fonts.body, fontSize: 13, marginTop: 4 },
  creditsRow: { flexDirection: 'row', alignItems: 'baseline' },
  creditsBig: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 34, fontWeight: '700' },
  remaining: { color: 'rgba(255,255,255,0.85)', fontFamily: fonts.body, fontSize: 14 },
  usedLine: { color: DASH_MINT_SOFT, fontFamily: fonts.body, fontSize: 13 },
  track: {
    height: DASH_BAR_HEIGHT,
    borderRadius: 999,
    overflow: 'hidden',
    marginTop: 4,
    backgroundColor: DASH_TRACK,
  },
  fill: { height: '100%', borderRadius: 999, backgroundColor: DASH_MINT },
  bottomRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: spacing.sm },
  renews: { color: DASH_MINT_SOFT, fontFamily: fonts.body, fontSize: 13, flex: 1 },
  buyBtn: {
    backgroundColor: DASH_MINT,
    borderRadius: DASH_BTN_RADIUS,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
  },
  buyText: { color: DASH_FOREST, fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '700' },
});
