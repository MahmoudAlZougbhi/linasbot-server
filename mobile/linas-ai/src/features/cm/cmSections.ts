/** Mobile CM section catalog — mirrors backend CM_SECTIONS (subset shown in app CM hub). */

export type CmSectionId =
  | 'ai_basics'
  | 'languages'
  | 'style'
  | 'dynamic_messages'
  | 'services'
  | 'branches'
  | 'opening_hours'
  | 'prices'
  | 'care'
  | 'knowledge'
  | 'handoff'
  | 'restricted'
  | 'comments'
  | 'off_days'
  | 'requests_appointments'
  /** Settings-hosted (not listed in CM hub). */
  | 'ai_limits';

export type CmSectionCard = {
  id: CmSectionId;
  title: string;
  description: string;
  /** false = show row but disabled with reason. */
  mobileSupported: boolean;
  disabledReason?: string;
  /** When false, hide from AI Setup hub (still editable elsewhere). */
  showInCmHub?: boolean;
};

export const CM_SECTION_CARDS: CmSectionCard[] = [
  {
    id: 'knowledge',
    title: 'Knowledge',
    description: 'Knowledge articles: title and note.',
    mobileSupported: true,
  },
  {
    id: 'ai_basics',
    title: 'AI Basics',
    description: 'Business name, AI name, role, and style.',
    mobileSupported: true,
  },
  {
    id: 'languages',
    title: 'Languages',
    description: 'Enable Arabic, English, French, Franco-Arabic.',
    mobileSupported: true,
    showInCmHub: false,
  },
  {
    id: 'style',
    title: 'Style & Tone',
    description: 'Tone, formality, and emoji level.',
    mobileSupported: true,
    showInCmHub: false,
  },
  {
    id: 'dynamic_messages',
    title: 'Greetings',
    description: 'Greeting rules with title and custom note (edited inside AI Basics).',
    mobileSupported: true,
    showInCmHub: false,
  },
  {
    id: 'services',
    title: 'Services',
    description: 'Legacy service catalog (name, note, available).',
    mobileSupported: true,
    showInCmHub: false,
  },
  {
    id: 'branches',
    title: 'Location and Opening Hours',
    description: 'Branches with map link and per-day opening hours.',
    mobileSupported: true,
  },
  {
    id: 'opening_hours',
    title: 'Opening Hours',
    description: 'Named schedules with Mon–Sun open hours or day off.',
    mobileSupported: true,
    showInCmHub: false,
  },
  {
    id: 'prices',
    title: 'Service',
    description: 'Service name with priced options (machine, body part, staff, price).',
    mobileSupported: true,
  },
  {
    id: 'care',
    title: 'Care',
    description: 'Preparation and aftercare articles.',
    mobileSupported: true,
    showInCmHub: false,
  },
  {
    id: 'handoff',
    title: 'Human Handoff',
    description: 'Contacts for when customers ask for a human.',
    mobileSupported: true,
    showInCmHub: false,
  },
  {
    id: 'restricted',
    title: 'Restricted',
    description: 'Topics the AI must refuse.',
    mobileSupported: true,
    showInCmHub: false,
  },
  {
    id: 'comments',
    title: 'Comments',
    description: 'Rules: reply on comment, reply via DM, or ignore.',
    mobileSupported: true,
  },
  {
    id: 'off_days',
    title: 'Off Days',
    description: 'Tap calendar days the business is closed.',
    mobileSupported: true,
    showInCmHub: false,
  },
  {
    id: 'requests_appointments',
    title: 'Requests & Appointments',
    description: 'الطلبات والمواعيد — orders, appointments, and other customer requests.',
    mobileSupported: true,
  },
  {
    id: 'ai_limits',
    title: 'Customer AI Limits',
    description: 'Protect credits by limiting each customer’s AI usage.',
    mobileSupported: true,
    showInCmHub: false,
  },
];

/** Hub sections excluded from progress/badge calculations (hidden or merged in hub). */
export const CM_HUB_PROGRESS_EXCLUDED: CmSectionId[] = [
  'languages',
  'style',
  'dynamic_messages',
  'services',
  'opening_hours',
  'off_days',
  'care',
  'handoff',
  'restricted',
];

export const CM_HUB_CARDS: CmSectionCard[] = CM_SECTION_CARDS.filter(
  (c) => c.showInCmHub !== false,
);

const BY_ID = Object.fromEntries(CM_SECTION_CARDS.map((c) => [c.id, c])) as Record<
  CmSectionId,
  CmSectionCard
>;

export function getCmSection(id: string): CmSectionCard | undefined {
  return BY_ID[id as CmSectionId];
}

export function isCmSectionId(id: string): id is CmSectionId {
  return id in BY_ID;
}

/** Alias used by CmScreen hub tiles. */
export type CmSectionMeta = CmSectionCard & { short: string };

export const CM_SECTION_TILES: CmSectionMeta[] = CM_HUB_CARDS.map((c) => ({
  ...c,
  short: c.description,
}));
