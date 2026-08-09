import { feather, type AppIconName } from '../../components/AppIcon';
import type { ControlArea } from '../control/controlAreas';

/**
 * Drawer / Control Center icons — DRW-01 handoff (thin-line grid tiles).
 * FAQ is a product module in the live app (not on the 8-tile PDF grid).
 */
export const MODULE_ICONS: Record<ControlArea, AppIconName> = {
  dashboard: feather('grid'),
  cm: feather('book-open'),
  faq: feather('help-circle'),
  livechat: feather('message-square'),
  integrations: feather('git-branch'),
  users: feather('users'),
  subscription: feather('credit-card'),
  usage: feather('cloud'),
  settings: feather('settings'),
  notifications: feather('bell'),
  owner: feather('shield'),
};

export const DRAWER_TOOL_ICONS = {
  search: feather('search'),
  notifications: feather('bell'),
  logout: feather('log-out'),
  close: feather('x'),
  pin: feather('bookmark'),
  overflow: feather('more-horizontal'),
} as const;
