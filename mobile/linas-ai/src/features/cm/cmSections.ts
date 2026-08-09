/** Mobile CM section catalog — mirrors dashboard cmSections.js + backend CM_SECTIONS. */

export type CmSectionId =
  | 'ai_basics'
  | 'languages'
  | 'style'
  | 'dynamic_messages'
  | 'services'
  | 'branches'
  | 'prices'
  | 'care'
  | 'knowledge'
  | 'faq'
  | 'handoff'
  | 'restricted'
  | 'actions'
  | 'ai_limits'
  | 'off_days';

export type CmSectionCard = {
  id: CmSectionId;
  title: string;
  description: string;
  /** false = show row but disabled with reason. */
  mobileSupported: boolean;
  disabledReason?: string;
};

export const CM_SECTION_CARDS: CmSectionCard[] = [
  {
    id: 'ai_basics',
    title: 'AI Basics',
    description: 'Business identity, persona, and core AI grounding.',
    mobileSupported: true,
  },
  {
    id: 'languages',
    title: 'Languages',
    description: 'Language policy and Franco → Arabic (RTL) answer map.',
    mobileSupported: true,
  },
  {
    id: 'style',
    title: 'Style & Tone',
    description: 'Voice, tone, and writing guidelines.',
    mobileSupported: true,
  },
  {
    id: 'dynamic_messages',
    title: 'Dynamic Messages',
    description: 'Greeting and system message templates.',
    mobileSupported: true,
  },
  {
    id: 'services',
    title: 'Services',
    description: 'Service / product catalog used by answers.',
    mobileSupported: true,
  },
  {
    id: 'branches',
    title: 'Locations',
    description: 'Branches, hours, and availability.',
    mobileSupported: true,
  },
  {
    id: 'prices',
    title: 'Prices',
    description: 'Catalog prices, policy text, and legacy price rows.',
    mobileSupported: true,
  },
  {
    id: 'care',
    title: 'Care / Instructions',
    description: 'Preparation and aftercare articles.',
    mobileSupported: true,
  },
  {
    id: 'knowledge',
    title: 'Knowledge',
    description: 'Narrative knowledge articles for retrieval.',
    mobileSupported: true,
  },
  {
    id: 'faq',
    title: 'FAQ',
    description: 'Linked Q&A groups (edit EN/AR on mobile).',
    mobileSupported: true,
  },
  {
    id: 'handoff',
    title: 'Human Handoff',
    description: 'Contacts and routing for human handoff.',
    mobileSupported: true,
  },
  {
    id: 'restricted',
    title: 'Restricted',
    description: 'Topics the AI must refuse.',
    mobileSupported: true,
  },
  {
    id: 'actions',
    title: 'Actions',
    description: 'Enable or disable AI capabilities.',
    mobileSupported: true,
  },
  {
    id: 'ai_limits',
    title: 'AI Limits',
    description: 'Per-customer image and context limits.',
    mobileSupported: true,
  },
  {
    id: 'off_days',
    title: 'Off Days',
    description: 'Closed weekdays and date ranges.',
    mobileSupported: true,
  },
];

/** Hub-only surfaces that exist on web but have no draft section API. */
export const CM_HUB_DISABLED = [
  {
    id: 'learning_inbox',
    title: 'Learning Inbox',
    reason: 'Available on the web dashboard only.',
  },
  {
    id: 'sources',
    title: 'Sources & Archive',
    reason: 'Available on the web dashboard only.',
  },
  {
    id: 'publish',
    title: 'Preview / Publish',
    reason: 'Validate and publish from the web dashboard or chat tools.',
  },
] as const;

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

/** Alias used by CmScreen hub tiles (parallel CM agent). */
export type CmSectionMeta = CmSectionCard & { short: string };

export const CM_SECTION_TILES: CmSectionMeta[] = CM_SECTION_CARDS.map((c) => ({
  ...c,
  short: c.description,
}));
