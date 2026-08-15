import type { DashboardNavigateTarget } from './dashboardTypes';
import type { Screen } from '../../app/navigation';

/** Map Dashboard card actions onto existing app screens (no dead buttons). */
export function screenForDashboardTarget(target: DashboardNavigateTarget): Screen {
  switch (target) {
    case 'chat':
      return { name: 'chat' };
    case 'subscription':
    case 'buy_credits':
      return { name: 'billing' };
    case 'choose_plan':
      return { name: 'billing', browsePlans: true };
    case 'integrations':
      return { name: 'integrations' };
    case 'cm':
      return { name: 'cm' };
    case 'faq':
      return { name: 'faq' };
    case 'users':
      return { name: 'users' };
  }
}
