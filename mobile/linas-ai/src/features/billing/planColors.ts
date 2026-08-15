import type { PlanId } from './planCatalog';

export type PlanColorTokens = {
  /** Accent bar, CTA fill, checkmarks, selected chip background. */
  accent: string;
  /** Plan name on light surfaces — AA contrast on white / #F9F9F9. */
  nameLight: string;
  /** Plan name on dark surfaces. */
  nameDark: string;
  /** Subtle badge / chip tint on light backgrounds. */
  softLight: string;
  /** Subtle badge / chip tint on dark backgrounds. */
  softDark: string;
  /** Plan name highlight on dashboard forest card (#064E3B). */
  nameOnForest: string;
};

/** Premium tier palette — forest/teal brand with distinct per-plan accents. */
export const PLAN_COLOR_TOKENS: Record<PlanId, PlanColorTokens> = {
  lite: {
    accent: '#64748B',
    nameLight: '#475569',
    nameDark: '#CBD5E1',
    softLight: '#F1F5F9',
    softDark: '#334155',
    nameOnForest: '#E2E8F0',
  },
  starter: {
    accent: '#008B8B',
    nameLight: '#006D6D',
    nameDark: '#5EEAD4',
    softLight: '#CCFBF1',
    softDark: '#134E4A',
    nameOnForest: '#5EEAD4',
  },
  growth: {
    accent: '#059669',
    nameLight: '#047857',
    nameDark: '#6EE7B7',
    softLight: '#D1FAE5',
    softDark: '#064E3B',
    nameOnForest: '#6EE7B7',
  },
  pro: {
    accent: '#6366F1',
    nameLight: '#4338CA',
    nameDark: '#A5B4FC',
    softLight: '#E0E7FF',
    softDark: '#312E81',
    nameOnForest: '#A5B4FC',
  },
  max: {
    accent: '#D97706',
    nameLight: '#B45309',
    nameDark: '#FCD34D',
    softLight: '#FEF3C7',
    softDark: '#78350F',
    nameOnForest: '#FCD34D',
  },
};

export function accentForPlan(id: PlanId): string {
  return PLAN_COLOR_TOKENS[id].accent;
}

export function planNameColor(id: PlanId, resolved: 'light' | 'dark'): string {
  return resolved === 'dark'
    ? PLAN_COLOR_TOKENS[id].nameDark
    : PLAN_COLOR_TOKENS[id].nameLight;
}

export function planSoftColor(id: PlanId, resolved: 'light' | 'dark'): string {
  return resolved === 'dark'
    ? PLAN_COLOR_TOKENS[id].softDark
    : PLAN_COLOR_TOKENS[id].softLight;
}

export function planNameOnForest(id: PlanId): string {
  return PLAN_COLOR_TOKENS[id].nameOnForest;
}

export function planOnAccent(_id: PlanId): string {
  return '#FFFFFF';
}
