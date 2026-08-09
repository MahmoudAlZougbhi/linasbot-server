export type ControlArea =
  | 'cm'
  | 'faq'
  | 'create'
  | 'integrations'
  | 'usage'
  | 'subscription'
  | 'users'
  | 'scheduled'
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
  group: 'operate' | 'grow' | 'account' | 'owner';
};

export const CONTROL_ITEMS: ControlItem[] = [
  {
    id: 'cm',
    title: 'Content Management',
    subtitle: 'Manual AI configuration',
    group: 'operate',
  },
  {
    id: 'faq',
    title: 'Smart Answers / FAQ',
    subtitle: 'Saved Q&A with auto-translate',
    group: 'operate',
  },
  {
    id: 'livechat',
    title: 'Live Chat',
    subtitle: 'Customer WhatsApp inbox',
    group: 'operate',
  },
  {
    id: 'notifications',
    title: 'Notifications',
    subtitle: 'Human request & escalation alerts',
    group: 'operate',
  },
  {
    id: 'integrations',
    title: 'Integrations',
    subtitle: 'Instagram & Facebook',
    group: 'operate',
  },
  {
    id: 'create',
    title: 'Creative Studio',
    subtitle: 'Full studio workspace',
    group: 'grow',
  },
  {
    id: 'scheduled',
    title: 'Scheduled',
    subtitle: 'Upcoming posts',
    group: 'grow',
  },
  {
    id: 'dashboard',
    title: 'Dashboard',
    subtitle: 'Metrics & health',
    group: 'grow',
  },
  {
    id: 'usage',
    title: 'Usage & Credits',
    subtitle: 'Included usage balance',
    group: 'account',
  },
  {
    id: 'subscription',
    title: 'Subscription',
    subtitle: 'Plans $24.99–$250 & entitlements',
    group: 'account',
  },
  {
    id: 'users',
    title: 'Users',
    subtitle: 'Members & permissions',
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
  operate: 'Operate',
  grow: 'Create & insights',
  account: 'Account',
  owner: 'Platform',
};
