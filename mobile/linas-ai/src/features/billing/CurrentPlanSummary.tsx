import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { StringKey } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { StatusChip } from '../../components/StatusChip';
import { isPlanId, type PlanId } from './planCatalog';
import { accentForPlan, planNameColor } from './planColors';
import { statusLabelKey } from './subscriptionCta';

type Props = {
  tr: (key: StringKey) => string;
  planId: string | null;
  status: string | null;
  periodEnd: number | null;
  messageBillingActive: boolean;
  includedMessages: number | null;
  includedRemaining: number | null;
  availableMessages: number | null;
  purchasedMessages: number | null;
  creditBalance: number | null;
  locale: string;
  onManage: () => void;
};

export function CurrentPlanSummary({
  tr,
  planId,
  status,
  periodEnd,
  messageBillingActive,
  includedMessages,
  includedRemaining,
  availableMessages,
  purchasedMessages,
  creditBalance,
  locale,
  onManage,
}: Props) {
  const { colors, resolved } = useTheme();
  if (!planId || !isPlanId(planId) || !status || status === 'none') {
    return null;
  }

  const dateLabel =
    periodEnd && Number.isFinite(periodEnd)
      ? new Date(periodEnd * 1000).toLocaleDateString(locale, {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
        })
      : tr('subDateUnknown');

  const statusKey = statusLabelKey(status);
  const tone =
    status === 'active' || status === 'trial'
      ? 'ok'
      : status === 'grace' || status === 'canceled'
        ? 'warn'
        : 'neutral';

  const planAccent = accentForPlan(planId);
  const nameColor = planNameColor(planId, resolved);

  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: planAccent }]}>
      <View style={styles.head}>
        <Text style={[styles.title, { color: colors.accentDeep }]}>{tr('subCurrentTitle')}</Text>
        <StatusChip label={tr(statusKey)} tone={tone} />
      </View>
      <Text style={[styles.plan, { color: nameColor }]}>
        {tr(planLabelKey(planId))}
      </Text>
      <Text style={[styles.meta, { color: colors.textMuted }]}>
        {status === 'canceled' ? tr('subAccessEnds') : tr('subRenewsOn')}: {dateLabel}
      </Text>
      <Text style={[styles.meta, { color: colors.textMuted }]}>
        {tr('subIncludedEachMonth').replace(
          '{n}',
          formatCredits(includedMessages, locale, tr('subCreditsMissing')),
        )}
      </Text>
      <Text style={[styles.meta, { color: colors.text }]}>
        {tr('subIncludedRemaining')}:{' '}
        {messageBillingActive
          ? formatCredits(includedRemaining, locale, tr('subCreditsMissing'))
          : tr('subMessagesPending')}
      </Text>
      <Text style={[styles.meta, { color: colors.text }]}>
        {tr('subPurchasedRemaining')}:{' '}
        {messageBillingActive
          ? formatCredits(purchasedMessages, locale, tr('subCreditsMissing'))
          : tr('subMessagesPending')}
      </Text>
      <Text style={[styles.meta, { color: colors.text }]}>
        {tr('subTotalAvailable')}:{' '}
        {messageBillingActive
          ? formatCredits(availableMessages, locale, tr('subCreditsMissing'))
          : tr('subMessagesPending')}
      </Text>
      {creditBalance != null ? (
        <Text style={[styles.meta, { color: colors.textMuted }]}>
          {tr('subLeftoverCredits').replace('{n}', creditBalance.toLocaleString(locale))}
        </Text>
      ) : null}
      <Pressable
        onPress={onManage}
        style={[styles.manage, { borderColor: colors.border }]}
        accessibilityRole="button"
        accessibilityLabel={tr('subManage')}
      >
        <Text style={[styles.manageText, { color: colors.accentDeep }]}>{tr('subManage')}</Text>
      </Pressable>
    </View>
  );
}

function planLabelKey(id: PlanId): StringKey {
  switch (id) {
    case 'lite':
      return 'subPlanLite';
    case 'starter':
      return 'subPlanStarter';
    case 'growth':
      return 'subPlanGrowth';
    case 'pro':
      return 'subPlanPro';
    case 'max':
      return 'subPlanMax';
  }
}

function formatCredits(value: number | null, locale: string, missing: string): string {
  if (value == null || !Number.isFinite(value)) return missing;
  return value.toLocaleString(locale);
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radii.lg,
    borderWidth: 1.5,
    padding: spacing.lg,
    gap: 6,
  },
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  title: { fontFamily: fonts.bodyMedium, fontSize: 13 },
  plan: { fontFamily: fonts.display, fontSize: 22 },
  meta: { fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  manage: {
    marginTop: 8,
    borderWidth: 1,
    borderRadius: radii.md,
    paddingVertical: 10,
    alignItems: 'center',
  },
  manageText: { fontFamily: fonts.bodyMedium, fontSize: 14 },
});
