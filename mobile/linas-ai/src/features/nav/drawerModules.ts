import type { StringKey } from '../../i18n/locales/en';
import type { ControlArea } from '../control/controlAreas';

export type DrawerModule = {
  id: ControlArea;
  titleKey: StringKey;
  /** Guests see the tile but taps open auth gate. */
  guestVisible: boolean;
  /** Hide unless entitled (Users). */
  entitlement?: 'users';
};

/** AI Setup — first tile in the 3×3 grid (highlighted). */
export const FEATURED_AI_SETUP: DrawerModule = {
  id: 'cm',
  titleKey: 'navContentManagement',
  guestVisible: true,
};

/**
 * 3×3 drawer grid order (Settings lives in footer).
 * Row 1: AI Setup · Dashboard · Follow up
 * Row 2: FAQ · Live Chat · Requests
 * Row 3: Integrations · Users · Subscription
 */
export const DRAWER_MODULES: DrawerModule[] = [
  { id: 'dashboard', titleKey: 'navDashboard', guestVisible: true },
  { id: 'smartFollowUp', titleKey: 'navSmartFollowUp', guestVisible: true },
  { id: 'faq', titleKey: 'faqTitle', guestVisible: true },
  { id: 'livechat', titleKey: 'navLiveChat', guestVisible: true },
  { id: 'requests', titleKey: 'navRequests', guestVisible: true },
  { id: 'integrations', titleKey: 'integrations', guestVisible: true },
  { id: 'users', titleKey: 'usersTitle', guestVisible: true, entitlement: 'users' },
  { id: 'subscription', titleKey: 'navSubscription', guestVisible: true },
];

export function visibleDrawerModules(opts: {
  showUsers: boolean;
}): DrawerModule[] {
  return DRAWER_MODULES.filter((m) => (m.entitlement === 'users' ? opts.showUsers : true));
}

/** Full 3×3 grid including featured AI Setup. */
export function drawerGridModules(opts: { showUsers: boolean }): DrawerModule[] {
  return [FEATURED_AI_SETUP, ...visibleDrawerModules(opts)];
}
