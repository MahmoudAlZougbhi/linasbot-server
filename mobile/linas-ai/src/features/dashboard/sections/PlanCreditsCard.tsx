import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, radii, spacing, useTheme } from '../../../theme';
import { isHighestPlan } from '../../billing/planCatalog';
import type { TenantDashboard } from '../dashboardTypes';

type Plan = TenantDashboard['plan_and_credits'];

type Props = {
  plan: Plan;
  onManageSubscription: () => void;
  onBuyCredits: () => void;
  onUpgrade: () => void;
};

function Metric({ label, value }: { label: string; value: string }) {
  const { colors } = useTheme();
  return (
    <View style={styles.metric}>
      <Text style={[styles.metricLabel, { color: colors.textDim }]}>{label}</Text>
      <Text style={[styles.metricValue, { color: colors.text }]}>{value}</Text>
    </View>
  );
}

export function PlanCreditsCard({ plan, onManageSubscription, onBuyCredits, onUpgrade }: Props) {
  const { colors } = useTheme();
  if (plan.availability === 'error' || plan.availability === 'unavailable') {
    return (
      <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Text style={[styles.title, { color: colors.text }]}>Plan and messages</Text>
        <Text style={{ color: colors.danger, fontFamily: fonts.body }}>
          {plan.message || 'Message data unavailable'}
        </Text>
      </View>
    );
  }

  const billingActive = Boolean(plan.message_billing_active);
  const available = billingActive ? plan.available_messages : null;
  const included = plan.included_messages ?? plan.intended_included_messages;
  const showUpgrade = !isHighestPlan(plan.plan_id);
  const showLeftoverBuy = !billingActive && plan.actions?.buy_credits !== false;
  const ratio =
    billingActive && typeof plan.usage_progress_ratio === 'number'
      ? Math.max(0, Math.min(1, plan.usage_progress_ratio))
      : null;

  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <Text style={[styles.title, { color: colors.text }]}>Plan and messages</Text>
      <Text style={{ color: colors.textMuted, fontFamily: fonts.body, marginBottom: 8 }}>
        {plan.plan_name || (plan.has_subscription ? plan.plan_id : 'No subscription')}
        {plan.subscription_status ? ` · ${plan.subscription_status}` : ''}
      </Text>
      {plan.current_period_end ? (
        <Text style={{ color: colors.textDim, fontFamily: fonts.body, fontSize: 12, marginBottom: 8 }}>
          Period ends {new Date(plan.current_period_end).toLocaleString()}
        </Text>
      ) : null}
      <View style={styles.grid}>
        <Metric
          label="Available"
          value={available == null ? 'Not active yet' : available.toLocaleString()}
        />
        <Metric
          label="Included / month"
          value={included == null ? 'Unavailable' : included.toLocaleString()}
        />
        <Metric
          label="Purchased"
          value={
            billingActive && plan.purchased_messages != null
              ? plan.purchased_messages.toLocaleString()
              : 'Not active yet'
          }
        />
        <Metric
          label="Reserved"
          value={
            billingActive && plan.reserved_messages != null
              ? plan.reserved_messages.toLocaleString()
              : 'Not active yet'
          }
        />
      </View>
      {plan.message_usage_note ? (
        <Text style={{ color: colors.textDim, fontFamily: fonts.body, fontSize: 12, marginTop: 8 }}>
          {plan.message_usage_note}
        </Text>
      ) : null}
      {plan.ai_setup_edits ? (
        <Text style={{ color: colors.textDim, fontFamily: fonts.body, fontSize: 12, marginTop: 8 }}>
          AI Setup edits {plan.ai_setup_edits.used}/{plan.ai_setup_edits.limit} today
          {plan.ai_setup_edits.reset_at ? ` · resets ${plan.ai_setup_edits.reset_at}` : ''}
        </Text>
      ) : null}
      {ratio != null ? (
        <View style={[styles.track, { backgroundColor: colors.progressTrack }]}>
          <View
            style={[styles.fill, { width: `${ratio * 100}%`, backgroundColor: colors.progressFill }]}
          />
        </View>
      ) : (
        <Text style={{ color: colors.textDim, fontFamily: fonts.body, fontSize: 12 }}>
          Usage progress unavailable
        </Text>
      )}
      <View style={styles.actions}>
        <Pressable onPress={onManageSubscription} accessibilityRole="button">
          <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>Manage subscription</Text>
        </Pressable>
        {showUpgrade ? (
          <Pressable onPress={onUpgrade} accessibilityRole="button">
            <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>Upgrade plan</Text>
          </Pressable>
        ) : null}
        {showLeftoverBuy ? (
          <Pressable onPress={onBuyCredits} accessibilityRole="button">
            <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>Add leftover credits</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radii.lg, borderWidth: 1, padding: spacing.lg, gap: spacing.sm },
  title: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  metric: { width: '45%', gap: 2 },
  metricLabel: { fontFamily: fonts.body, fontSize: 11 },
  metricValue: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  track: { height: 8, borderRadius: 999, overflow: 'hidden', marginTop: 4 },
  fill: { height: '100%', borderRadius: 999 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md, marginTop: spacing.sm },
});
