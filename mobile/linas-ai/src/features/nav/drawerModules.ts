import type { ControlArea } from '../control/controlAreas';

export type DrawerModule = {
  id: ControlArea;
  title: string;
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
  { id: 'dashboard', title: 'Dashboard', guestVisible: true },
  { id: 'cm', title: 'Content Management', guestVisible: true },
  { id: 'faq', title: 'Smart Answers / FAQ', guestVisible: true },
  { id: 'livechat', title: 'Live Chat', guestVisible: true },
  { id: 'integrations', title: 'Integrations', guestVisible: true },
  { id: 'users', title: 'Users', guestVisible: true, entitlement: 'users' },
  { id: 'subscription', title: 'Subscription', guestVisible: true },
  { id: 'usage', title: 'Usage & Credits', guestVisible: true },
  { id: 'settings', title: 'Settings', guestVisible: true },
];

export function visibleDrawerModules(opts: {
  showUsers: boolean;
}): DrawerModule[] {
  return DRAWER_MODULES.filter((m) => (m.entitlement === 'users' ? opts.showUsers : true));
}
