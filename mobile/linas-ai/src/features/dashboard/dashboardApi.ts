import { ApiError, apiFetch } from '../../api/client';
import { isNetworkFailure } from '../../api/networkError';

import {
  TenantDashboard,
  TenantDashboardSchema,
  type DashboardNavigateTarget,
} from './dashboardTypes';
import {
  dashboardQueryRange,
  namedDashboardApiPeriod,
  type DashboardPeriodSelection,
} from './dashboardFormat';

export async function fetchTenantDashboard(
  period: DashboardPeriodSelection,
  tz: string,
): Promise<TenantDashboard> {
  const params = new URLSearchParams({ tz });
  const named = namedDashboardApiPeriod(period);
  if (named) {
    // Named periods are resolved in the tenant timezone on the server.
    // Do not send custom start/end (exclusive end + same-day/UTC month bugs).
    params.set('period', named);
  } else {
    const range = dashboardQueryRange(period);
    params.set('period', 'custom');
    params.set('start', range.start);
    params.set('end', range.end);
  }
  return apiFetch(`/api/mobile/dashboard?${params.toString()}`, {
    schema: TenantDashboardSchema,
  });
}

export function classifyDashboardError(err: unknown): 'auth' | 'forbidden' | 'offline' | 'other' {
  if (isNetworkFailure(err)) return 'offline';
  if (err instanceof ApiError) {
    if (err.status === 401) return 'auth';
    if (err.status === 403) return 'forbidden';
  }
  return 'other';
}

export function dashboardErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return 'You do not have permission to view this dashboard.';
    if (err.status === 401) return 'Not authenticated.';
    if (err.status === 400) return 'Invalid period or timezone.';
  }
  if (err instanceof Error && err.message) return err.message;
  return 'Could not load the dashboard.';
}

export function resolveDashboardAction(code: string | null | undefined): DashboardNavigateTarget | null {
  switch (code) {
    case 'complete_setup':
    case 'publish_cm':
    case 'open_cm':
    case 'continue_setup':
      return 'cm';
    case 'connect_instagram':
    case 'connect_facebook':
    case 'review_permissions':
    case 'manage_integrations':
      return 'integrations';
    case 'renew_subscription':
    case 'manage_subscription':
      return 'subscription';
    case 'upgrade_plan':
      return 'choose_plan';
    case 'buy_credits':
      return 'buy_credits';
    case 'review_faq':
      return 'faq';
    case 'manage_users':
      return 'users';
    case 'contact_support':
      return 'chat';
    default:
      return null;
  }
}
