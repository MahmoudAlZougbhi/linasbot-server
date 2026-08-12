export type ControlArea =
  | 'cm'
  | 'faq'
  | 'integrations'
  | 'usage'
  | 'subscription'
  | 'users'
  | 'settings'
  | 'dashboard'
  | 'smartFollowUp'
  | 'livechat'
  | 'requests'
  | 'notifications'
  | 'owner';

export type ControlItem = {
  id: ControlArea;
  title: string;
  subtitle: string;
  ownerOnly?: boolean;
  group: 'operate' | 'account' | 'owner';
};

/** Product module order matches drawerModules (no Creative / Team alias). */
export const CONTROL_ITEMS: ControlItem[] = [
  { id: 'dashboard', title: 'Dashboard / Status', subtitle: 'Workspace health & usage', group: 'operate' },
  { id: 'cm', title: 'AI Setup', subtitle: 'What your customer AI knows', group: 'operate' },
  {
    id: 'smartFollowUp',
    title: 'Smart Follow-Up',
    subtitle: 'Auto follow-up when WhatsApp customers go quiet',
    group: 'operate',
  },
  {
    id: 'faq',
    title: 'Smart Answers / FAQ',
    subtitle: 'Ready-made Q&A — saves AI cost',
    group: 'operate',
  },
  { id: 'livechat', title: 'Live Chat', subtitle: 'Read-only IG/FB inbox', group: 'operate' },
  {
    id: 'requests',
    title: 'Requests',
    subtitle: 'Customer orders & appointments',
    group: 'operate',
  },
  { id: 'integrations', title: 'Integrations', subtitle: 'Instagram & Facebook', group: 'operate' },
  { id: 'users', title: 'Users', subtitle: 'Members & permissions', group: 'account' },
  { id: 'subscription', title: 'Subscription', subtitle: 'Plans & billing', group: 'account' },
  { id: 'settings', title: 'Settings', subtitle: 'Preferences & legal', group: 'account' },
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
  account: 'Account',
  owner: 'Platform',
};
