import type { PlanId } from './planCatalog';

export type PlanNameContext = 'light' | 'dark' | 'forest';

export type PlanColorTokens = {
  /** Canonical plan tier color — accent bar, CTA fill, plan name on light surfaces. */
  accent: string;
  /** Plan name on light surfaces (same hue as accent). */
  nameLight: string;
  /** Plan name on dark subscription surfaces. */
  nameDark: string;
  /** Subtle badge / chip tint on light backgrounds. */
  softLight: string;
  /** Subtle badge / chip tint on dark backgrounds. */
  softDark: string;
  /** Plan name on dashboard forest card (#064E3B) — light tint of accent hue. */
  nameOnForest: string;
};

/** Premium tier palette — one canonical accent per plan, contrast variants per surface. */
export const PLAN_COLOR_TOKENS: Record<PlanId, PlanColorTokens> = {
  lite: {
    accent: '#64748B',
    nameLight: '#64748B',
    nameDark: '#CBD5E1',
    softLight: '#F1F5F9',
    softDark: '#334155',
    nameOnForest: '#CBD5E1',
  },
  starter: {
    accent: '#008B8B',
    nameLight: '#008B8B',
    nameDark: '#5EEAD4',
    softLight: '#CCFBF1',
    softDark: '#134E4A',
    nameOnForest: '#5EEAD4',
  },
  growth: {
    accent: '#059669',
    nameLight: '#059669',
    nameDark: '#6EE7B7',
    softLight: '#D1FAE5',
    softDark: '#064E3B',
    nameOnForest: '#6EE7B7',
  },
  pro: {
    accent: '#6366F1',
    nameLight: '#6366F1',
    nameDark: '#A5B4FC',
    softLight: '#E0E7FF',
    softDark: '#312E81',
    nameOnForest: '#A5B4FC',
  },
  max: {
    accent: '#D97706',
    nameLight: '#D97706',
    nameDark: '#FCD34D',
    softLight: '#FEF3C7',
    softDark: '#78350F',
    nameOnForest: '#FCD34D',
  },
};

export function accentForPlan(id: PlanId): string {
  return PLAN_COLOR_TOKENS[id].accent;
}

/** Plan name color for subscription (light/dark) or dashboard forest card. */
export function planNameColor(id: PlanId, context: PlanNameContext = 'light'): string {
  const tokens = PLAN_COLOR_TOKENS[id];
  switch (context) {
    case 'dark':
      return tokens.nameDark;
    case 'forest':
      return tokens.nameOnForest;
    default:
      return tokens.nameLight;
  }
}

export function planSoftColor(id: PlanId, resolved: 'light' | 'dark'): string {
  return resolved === 'dark'
    ? PLAN_COLOR_TOKENS[id].softDark
    : PLAN_COLOR_TOKENS[id].softLight;
}

export function planOnAccent(_id: PlanId): string {
  return '#FFFFFF';
}
