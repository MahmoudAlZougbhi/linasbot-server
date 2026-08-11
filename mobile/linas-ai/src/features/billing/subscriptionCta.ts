import type { StringKey } from '../../i18n';
import { type PlanId, PLAN_CATALOG, planRank } from './planCatalog';

export type EntitlementStatus =
  | 'none'
  | 'active'
  | 'trial'
  | 'grace'
  | 'canceled'
  | 'expired'
  | 'refunded'
  | 'revoked'
  | 'pending'
  | string;

export type CtaKind = 'choose' | 'upgrade' | 'current' | 'switch_renewal' | 'disabled';

export type PlanCta = {
  kind: CtaKind;
  labelKey: StringKey;
  enabled: boolean;
};

const CTA_CHOOSE: Record<PlanId, StringKey> = {
  lite: 'subCtaChooseLite',
  starter: 'subCtaChooseStarter',
  growth: 'subCtaChooseGrowth',
  pro: 'subCtaChoosePro',
  max: 'subCtaChooseMax',
};

const CTA_UPGRADE: Record<PlanId, StringKey> = {
  lite: 'subCtaChooseLite',
  starter: 'subCtaUpgradeStarter',
  growth: 'subCtaUpgradeGrowth',
  pro: 'subCtaUpgradePro',
  max: 'subCtaUpgradeMax',
};

const CTA_SWITCH: Record<PlanId, StringKey> = {
  lite: 'subCtaSwitchLite',
  starter: 'subCtaSwitchStarter',
  growth: 'subCtaSwitchGrowth',
  pro: 'subCtaSwitchPro',
  max: 'subCtaSwitchMax',
};

export function statusLabelKey(status: EntitlementStatus | null | undefined): StringKey {
  switch ((status || 'none').toLowerCase()) {
    case 'active':
      return 'subStatusActive';
    case 'trial':
      return 'subStatusTrial';
    case 'grace':
      return 'subStatusGrace';
    case 'canceled':
      return 'subStatusCanceled';
    case 'expired':
      return 'subStatusExpired';
    case 'refunded':
      return 'subStatusRefunded';
    case 'revoked':
      return 'subStatusRevoked';
    case 'pending':
      return 'subStatusPending';
    default:
      return 'subStatusNone';
  }
}

export function isPaidActiveStatus(status: EntitlementStatus | null | undefined): boolean {
  const s = (status || '').toLowerCase();
  return s === 'active' || s === 'trial' || s === 'grace' || s === 'canceled';
}

/** canceled still has access until period end — treat as current for CTA. */
export function resolvePlanCta(
  target: PlanId,
  currentPlan: PlanId | null,
  status: EntitlementStatus | null | undefined,
  opts: {
    storePriceAvailable: boolean;
    purchasePending: boolean;
  },
): PlanCta {
  const { storePriceAvailable, purchasePending } = opts;
  if (purchasePending) {
    return { kind: 'disabled', labelKey: 'subCtaPending', enabled: false };
  }
  const paid = isPaidActiveStatus(status) && currentPlan != null;
  if (paid && currentPlan === target) {
    return { kind: 'current', labelKey: 'subCtaCurrent', enabled: false };
  }
  if (!storePriceAvailable) {
    return { kind: 'disabled', labelKey: 'subCtaUnavailable', enabled: false };
  }
  if (!paid || !currentPlan) {
    return { kind: 'choose', labelKey: CTA_CHOOSE[target], enabled: true };
  }
  const curRank = planRank(currentPlan);
  const nextRank = planRank(target);
  if (nextRank > curRank) {
    return { kind: 'upgrade', labelKey: CTA_UPGRADE[target], enabled: true };
  }
  return { kind: 'switch_renewal', labelKey: CTA_SWITCH[target], enabled: true };
}

export function accentForPlan(id: PlanId): string {
  switch (id) {
    case 'lite':
      return '#0D9488';
    case 'starter':
      return '#0891B2';
    case 'growth':
      return '#2563EB';
    case 'pro':
      return '#7C3AED';
    case 'max':
      return '#DB2777';
    default:
      return PLAN_CATALOG.lite.catalogPriceUsd ? '#0D9488' : '#0D9488';
  }
}
