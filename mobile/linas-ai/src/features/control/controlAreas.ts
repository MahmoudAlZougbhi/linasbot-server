export type ControlArea =
  | 'cm'
  | 'integrations'
  | 'usage'
  | 'subscription'
  | 'users'
  | 'settings'
  | 'dashboard'
  | 'livechat'
  | 'notifications'
  | 'owner';

export type ControlItem = {
  id: ControlArea;
  title: string;
  subtitle: string;
  ownerOnly?: boolean;
  group: 'operate' | 'insights' | 'account' | 'owner';
};

/** Product sections first (no Creative Studio / Scheduled). */
export const CONTROL_ITEMS: ControlItem[] = [
  {
    id: 'dashboard',
    title: 'Dashboard / Status',
    subtitle: 'Metrics & health',
    group: 'operate',
  },
  {
    id: 'cm',
    title: 'Content Management',
    subtitle: 'What your customer AI knows',
    group: 'operate',
  },
  {
    id: 'livechat',
    title: 'Live Chat',
    subtitle: 'Read-only IG/FB inbox',
    group: 'operate',
  },
  {
    id: 'integrations',
    title: 'Integrations',
    subtitle: 'Instagram & Facebook',
    group: 'operate',
  },
  {
    id: 'notifications',
    title: 'Notifications',
    subtitle: 'Escalation alerts',
    group: 'insights',
  },
  {
    id: 'users',
    title: 'Users',
    subtitle: 'Members & permissions',
    group: 'account',
  },
  {
    id: 'subscription',
    title: 'Subscription',
    subtitle: 'Plans & entitlements',
    group: 'account',
  },
  {
    id: 'usage',
    title: 'Usage & Credits',
    subtitle: 'Included usage balance',
    group: 'account',
  },
  {
    id: 'settings',
    title: 'Settings',
    subtitle: 'Legal links & version',
    group: 'account',
  },
  {
    id: 'owner',
    title: 'Owner Control Center',
    subtitle: 'Platform metrics',
    ownerOnly: true,
    group: 'owner',
  },
];

export const GROUP_LABELS: Record<ControlItem['group'], string> = {
  operate: 'Product',
  insights: 'Alerts',
  account: 'Account',
  owner: 'Platform',
};
