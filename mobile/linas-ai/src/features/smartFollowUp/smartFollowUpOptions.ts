import type { FollowUpGoal } from './smartFollowUpApi';

export const FOLLOWUP_CHANNEL_IDS = [
  'instagram_dm',
  'facebook_messenger',
  'whatsapp_cloud',
  'web_chat',
  'tiktok',
] as const;

export type FollowUpChannelId = (typeof FOLLOWUP_CHANNEL_IDS)[number];
export type FollowUpChannelKey = Exclude<FollowUpChannelId, 'tiktok'>;

export type FollowUpChannelsEnabled = Record<FollowUpChannelKey, boolean>;

export const DEFAULT_CHANNELS_ENABLED: FollowUpChannelsEnabled = {
  instagram_dm: true,
  facebook_messenger: true,
  whatsapp_cloud: true,
  web_chat: true,
};

export type ChannelTileDef = {
  id: FollowUpChannelId;
  labelKey: 'sfuChannelInstagram' | 'sfuChannelFacebook' | 'sfuChannelWhatsApp' | 'sfuChannelWeb' | 'sfuChannelTikTok';
  iconFamily: 'ion' | 'mci';
  iconName: string;
  iconColor: string;
  supported: boolean;
};

export const CHANNEL_TILES: ChannelTileDef[] = [
  {
    id: 'instagram_dm',
    labelKey: 'sfuChannelInstagram',
    iconFamily: 'ion',
    iconName: 'logo-instagram',
    iconColor: '#E4405F',
    supported: true,
  },
  {
    id: 'facebook_messenger',
    labelKey: 'sfuChannelFacebook',
    iconFamily: 'ion',
    iconName: 'logo-facebook',
    iconColor: '#1877F2',
    supported: true,
  },
  {
    id: 'whatsapp_cloud',
    labelKey: 'sfuChannelWhatsApp',
    iconFamily: 'ion',
    iconName: 'logo-whatsapp',
    iconColor: '#25D366',
    supported: true,
  },
  {
    id: 'web_chat',
    labelKey: 'sfuChannelWeb',
    iconFamily: 'ion',
    iconName: 'globe-outline',
    iconColor: '#0D9488',
    supported: true,
  },
  {
    id: 'tiktok',
    labelKey: 'sfuChannelTikTok',
    iconFamily: 'mci',
    iconName: 'music-note',
    iconColor: '#111111',
    supported: false,
  },
];

export type DelayOption = { label: string; minutes: number };

export const DELAY_OPTIONS: DelayOption[] = [
  { label: '15 min', minutes: 15 },
  { label: '30 min', minutes: 30 },
  { label: '1 hour', minutes: 60 },
  { label: '2 hours', minutes: 120 },
  { label: '6 hours', minutes: 360 },
  { label: '12 hours', minutes: 720 },
  { label: '20 hours', minutes: 1200 },
];

export function delayOptionsForValue(minutes: number): DelayOption[] {
  const match = DELAY_OPTIONS.find((o) => o.minutes === minutes);
  if (match) return DELAY_OPTIONS;
  return [...DELAY_OPTIONS, { label: formatDelayOptionLabel(minutes), minutes }].sort(
    (a, b) => a.minutes - b.minutes,
  );
}

export function formatDelayOptionLabel(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const hours = minutes / 60;
  if (Number.isInteger(hours)) return `${hours} hour${hours === 1 ? '' : 's'}`;
  return `${Math.round(hours * 10) / 10} hours`;
}

export const GOAL_OPTIONS: { value: FollowUpGoal; labelKey: 'sfuGoalGentleCheckIn' | 'sfuGoalOfferMoreHelp' | 'sfuGoalPolitelyClose' }[] = [
  { value: 'gentle_check_in', labelKey: 'sfuGoalGentleCheckIn' },
  { value: 'offer_more_help', labelKey: 'sfuGoalOfferMoreHelp' },
  { value: 'politely_close', labelKey: 'sfuGoalPolitelyClose' },
];

export function normalizeChannelsEnabled(
  raw: Partial<FollowUpChannelsEnabled> | undefined,
): FollowUpChannelsEnabled {
  return {
    instagram_dm: raw?.instagram_dm ?? DEFAULT_CHANNELS_ENABLED.instagram_dm,
    facebook_messenger: raw?.facebook_messenger ?? DEFAULT_CHANNELS_ENABLED.facebook_messenger,
    whatsapp_cloud: raw?.whatsapp_cloud ?? DEFAULT_CHANNELS_ENABLED.whatsapp_cloud,
    web_chat: raw?.web_chat ?? DEFAULT_CHANNELS_ENABLED.web_chat,
  };
}

export function supportedChannelsSelected(channels: FollowUpChannelsEnabled): boolean {
  return Object.values(channels).some(Boolean);
}
