import { feather, mci, type AppIconName } from '../../components/AppIcon';
import type { ControlArea } from '../control/controlAreas';

/**
 * Drawer / Control Center icons — DRW-01 handoff (thin-line grid tiles).
 * FAQ is a product module in the live app (not on the 8-tile PDF grid).
 * Team in the PDF maps to Users here.
 */
export const MODULE_ICONS: Record<ControlArea, AppIconName> = {
  dashboard: feather('grid'),
  cm: feather('book-open'),
  faq: feather('help-circle'),
  livechat: feather('message-square'),
  integrations: mci('power-plug-outline'),
  users: feather('users'),
  subscription: feather('credit-card'),
  usage: feather('upload-cloud'),
  settings: feather('settings'),
  notifications: feather('bell'),
  owner: feather('shield'),
};

export const DRAWER_TOOL_ICONS = {
  search: feather('search'),
  logout: feather('log-out'),
  close: feather('x'),
  pin: feather('bookmark'),
  overflow: feather('more-horizontal'),
  newChat: feather('plus'),
} as const;
