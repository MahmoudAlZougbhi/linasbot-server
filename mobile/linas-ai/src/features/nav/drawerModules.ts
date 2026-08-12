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

/** Featured full-width tile above the module grid (not in DRAWER_MODULES). */
export const FEATURED_AI_SETUP: DrawerModule = {
  id: 'cm',
  titleKey: 'navContentManagement',
  guestVisible: true,
};

/**
 * Binding product-module order.
 * AI Setup is featured separately (full width). Notifications and Logout live in Settings.
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
  { id: 'settings', titleKey: 'settings', guestVisible: true },
];

export function visibleDrawerModules(opts: {
  showUsers: boolean;
}): DrawerModule[] {
  return DRAWER_MODULES.filter((m) => (m.entitlement === 'users' ? opts.showUsers : true));
}
