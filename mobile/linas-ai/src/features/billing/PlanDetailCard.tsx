import { StyleSheet, Text, View } from 'react-native';

import { LinasSparkleIcon } from '../../components/LinasSparkleIcon';
import type { StringKey } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { PlanIncludedList } from './PlanIncludedList';
import { PlanNotIncluded } from './PlanNotIncluded';
import { SmartAnswersInfo } from './SmartAnswersInfo';
import type { PlanId } from './planCatalog';
import {
  entitlementsForPlanId,
  PLAN_BADGE_KEY,
  PLAN_NAME_KEY,
  PLAN_TAGLINE_KEY,
} from './planEntitlements';

type Props = {
  planId: PlanId;
  priceLabel: string;
  periodSuffix: string;
  locale: string;
  tr: (key: StringKey) => string;
};

export function PlanDetailCard({ planId, priceLabel, periodSuffix, locale, tr }: Props) {
  const { colors } = useTheme();
  const ents = entitlementsForPlanId(planId);
  const credits = ents.includedCredits.toLocaleString(locale);
  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <View style={[styles.badge, { backgroundColor: colors.mintSoft }]}>
        <Text style={[styles.badgeText, { color: colors.accent }]}>{tr(PLAN_BADGE_KEY[planId])}</Text>
      </View>
      <View style={styles.head}>
        <Text style={[styles.name, { color: colors.text }]}>{tr(PLAN_NAME_KEY[planId])}</Text>
        <Text style={[styles.price, { color: colors.text }]}>
          {priceLabel}
          <Text style={[styles.period, { color: colors.textMuted }]}> {periodSuffix}</Text>
        </Text>
      </View>
      <Text style={[styles.tagline, { color: colors.textMuted }]}>{tr(PLAN_TAGLINE_KEY[planId])}</Text>

      <View style={[styles.credits, { backgroundColor: colors.surfaceAlt }]}>
        <LinasSparkleIcon size={18} color={colors.accent} />
        <Text style={[styles.creditsText, { color: colors.accent }]}>
          <Text style={styles.creditsStrong}>{credits}</Text>
          {` ${tr('subAiCreditsIncluded')}`}
        </Text>
      </View>

      <PlanIncludedList
        title={tr('subIncluded')}
        rows={ents.included}
        tr={tr}
        locale={locale}
        variant="choose"
      />
      <SmartAnswersInfo tr={tr} variant="choose" />
      <PlanNotIncluded ids={ents.excluded} tr={tr} variant="choose" />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radii.lg,
    borderWidth: 1,
    padding: spacing.lg,
    gap: spacing.md,
  },
  badge: {
    alignSelf: 'flex-start',
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  badgeText: {
    fontFamily: fonts.bodyMedium,
    fontSize: 10,
    letterSpacing: 0.6,
    fontWeight: '700',
  },
  head: { gap: 4 },
  name: { fontFamily: fonts.display, fontSize: 28, fontWeight: '700' },
  price: { fontFamily: fonts.display, fontSize: 28, fontWeight: '700' },
  period: { fontFamily: fonts.body, fontSize: 16, fontWeight: '400' },
  tagline: { fontFamily: fonts.body, fontSize: 15, lineHeight: 21 },
  credits: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: radii.md,
    paddingHorizontal: 12,
    paddingVertical: 12,
  },
  creditsText: { flex: 1, fontFamily: fonts.body, fontSize: 15, lineHeight: 20 },
  creditsStrong: { fontFamily: fonts.bodyMedium, fontWeight: '700' },
});
