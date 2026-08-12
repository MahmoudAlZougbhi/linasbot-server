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
  | 'actions'
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
    id: 'ai_basics',
    title: 'AI Basics',
    description: 'Role, business purpose, and short introduction.',
    mobileSupported: true,
  },
  {
    id: 'languages',
    title: 'Languages',
    description: 'Enable Arabic, English, French, Franco-Arabic.',
    mobileSupported: true,
  },
  {
    id: 'style',
    title: 'Style & Tone',
    description: 'Tone, formality, and emoji level.',
    mobileSupported: true,
  },
  {
    id: 'dynamic_messages',
    title: 'Greetings & Messages',
    description: 'Greeting and system message templates.',
    mobileSupported: true,
  },
  {
    id: 'services',
    title: 'Services',
    description: 'Service catalog: name, note, available.',
    mobileSupported: true,
  },
  {
    id: 'branches',
    title: 'Locations',
    description: 'Branches with address and Maps link.',
    mobileSupported: true,
  },
  {
    id: 'opening_hours',
    title: 'Opening Hours',
    description: 'Named schedules with Mon–Sun open hours or day off.',
    mobileSupported: true,
  },
  {
    id: 'prices',
    title: 'Prices',
    description: 'Build reusable price list catalogs.',
    mobileSupported: true,
  },
  {
    id: 'care',
    title: 'Care',
    description: 'Preparation and aftercare articles.',
    mobileSupported: true,
  },
  {
    id: 'knowledge',
    title: 'Knowledge',
    description: 'Knowledge articles: title and note.',
    mobileSupported: true,
  },
  {
    id: 'handoff',
    title: 'Human Handoff',
    description: 'Contacts for when customers ask for a human.',
    mobileSupported: true,
  },
  {
    id: 'restricted',
    title: 'Restricted',
    description: 'Topics the AI must refuse.',
    mobileSupported: true,
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
  },
  {
    id: 'requests_appointments',
    title: 'Requests & Appointments',
    description: 'الطلبات والمواعيد — orders, appointments, and other customer requests.',
    mobileSupported: true,
  },
  {
    id: 'actions',
    title: 'Actions',
    description: 'Enable Instagram, Facebook, handoff, and more.',
    mobileSupported: true,
    showInCmHub: false,
  },
  {
    id: 'ai_limits',
    title: 'AI Limits',
    description: 'Image and context usage limits.',
    mobileSupported: true,
    showInCmHub: false,
  },
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
