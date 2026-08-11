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

/**
 * Binding product-module order (Mahmoud prompt §6).
 * Notifications and Logout live in Settings, not this grid or the drawer footer.
 */
export const DRAWER_MODULES: DrawerModule[] = [
  { id: 'dashboard', titleKey: 'navDashboard', guestVisible: true },
  { id: 'cm', titleKey: 'navContentManagement', guestVisible: true },
  { id: 'faq', titleKey: 'faqTitle', guestVisible: true },
  { id: 'livechat', titleKey: 'navLiveChat', guestVisible: true },
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
