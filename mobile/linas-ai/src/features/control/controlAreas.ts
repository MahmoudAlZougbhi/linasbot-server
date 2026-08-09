export type ControlArea =
  | 'cm'
  | 'create'
  | 'integrations'
  | 'usage'
  | 'subscription'
  | 'users'
  | 'scheduled'
  | 'settings'
  | 'dashboard'
  | 'livechat'
  | 'comments'
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
    id: 'livechat',
    title: 'Live Chat',
    subtitle: 'Operator inbox (ops)',
    group: 'operate',
  },
  {
    id: 'comments',
    title: 'Comments',
    subtitle: 'Not live-verified yet',
    group: 'operate',
  },
  {
    id: 'integrations',
    title: 'Integrations',
    subtitle: 'Meta readiness (truthful)',
    group: 'operate',
  },
  {
    id: 'create',
    title: 'Create Post',
    subtitle: 'Creative Studio',
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
    title: 'Billing',
    subtitle: 'Plan & entitlements',
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
