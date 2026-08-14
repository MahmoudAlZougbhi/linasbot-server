/**
 * Included / not-included rows from the frozen catalog flags.
 * Channel flags, FAQ cap, seats, and monthly credits must match planCatalog.ts
 * and services.membership.plan_catalog.
 */
import type { StringKey } from '../../i18n';
import { PLAN_CATALOG, PLAN_ORDER, type PlanDefinition, type PlanId } from './planCatalog';

export type FeatureIcon =
  | 'chat'
  | 'send'
  | 'bookmark'
  | 'quotes'
  | 'person'
  | 'whatsapp'
  | 'tiktok';

export type IncludedRow = {
  id: string;
  icon: FeatureIcon;
  labelKey: StringKey;
  count?: number;
};

export type ExcludedId = 'comments' | 'whatsapp' | 'tiktok';

export type PlanEntitlements = {
  planId: PlanId;
  includedCredits: number;
  faqCapacity: number;
  included: IncludedRow[];
  excluded: ExcludedId[];
};

const EXCLUDED_LABEL: Record<ExcludedId, StringKey> = {
  comments: 'subNotComments',
  whatsapp: 'subNotWhatsApp',
  tiktok: 'subNotTikTok',
};

export function excludedLabelKey(id: ExcludedId): StringKey {
  return EXCLUDED_LABEL[id];
}

export function entitlementsForPlan(plan: PlanDefinition): PlanEntitlements {
  const included: IncludedRow[] = [];
  const excluded: ExcludedId[] = [];

  if (plan.commentAutomation) {
    included.push({
      id: 'dms_comments',
      icon: 'send',
      labelKey: 'subFeatDmComments',
    });
  } else {
    included.push({ id: 'dms', icon: 'send', labelKey: 'subFeatDmOnly' });
    excluded.push('comments');
  }

  if (plan.whatsapp) {
    included.push({ id: 'whatsapp', icon: 'whatsapp', labelKey: 'subFeatWhatsApp' });
  } else {
    excluded.push('whatsapp');
  }

  if (plan.tiktok) {
    included.push({ id: 'tiktok', icon: 'tiktok', labelKey: 'subFeatTikTok' });
  } else {
    excluded.push('tiktok');
  }

  included.push({
    id: 'smart_answers',
    icon: 'quotes',
    labelKey: 'subFeatSmartAnswers',
    count: plan.faqCapacity,
  });

  if (plan.additionalSeats === 0) {
    included.push({ id: 'seats', icon: 'person', labelKey: 'subFeatOwnerAccount' });
  } else if (plan.additionalSeats == null) {
    included.push({ id: 'seats', icon: 'person', labelKey: 'subFeatUnlimitedSeats' });
  } else {
    included.push({
      id: 'seats',
      icon: 'person',
      labelKey: 'subFeatExtraSeats',
      count: plan.additionalSeats,
    });
  }

  return {
    planId: plan.id,
    includedCredits: plan.includedCredits,
    faqCapacity: plan.faqCapacity,
    included,
    excluded,
  };
}

export function entitlementsForPlanId(id: PlanId): PlanEntitlements {
  return entitlementsForPlan(PLAN_CATALOG[id]);
}

export const PLAN_BADGE_KEY: Record<PlanId, StringKey> = {
  lite: 'subBadgeLite',
  starter: 'subBadgeStarter',
  growth: 'subBadgeGrowth',
  pro: 'subBadgePro',
  max: 'subBadgeMax',
};

export const PLAN_NAME_KEY: Record<PlanId, StringKey> = {
  lite: 'subPlanLite',
  starter: 'subPlanStarter',
  growth: 'subPlanGrowth',
  pro: 'subPlanPro',
  max: 'subPlanMax',
};

export const PLAN_TAGLINE_KEY: Record<PlanId, StringKey> = {
  lite: 'subLiteTagline',
  starter: 'subStarterTagline',
  growth: 'subGrowthTagline',
  pro: 'subProTagline',
  max: 'subMaxTagline',
};

export const PLAN_CHOOSE_CTA: Record<PlanId, StringKey> = {
  lite: 'subCtaChooseLite',
  starter: 'subCtaChooseStarter',
  growth: 'subCtaChooseGrowth',
  pro: 'subCtaChoosePro',
  max: 'subCtaChooseMax',
};

export function allPlanEntitlements(): PlanEntitlements[] {
  return PLAN_ORDER.map((id) => entitlementsForPlanId(id));
}

export function currentPlanIncludeIcons(row: IncludedRow): FeatureIcon {
  if (row.id === 'dms' || row.id === 'dms_comments') return 'chat';
  if (row.id === 'smart_answers') return 'bookmark';
  return row.icon;
}
