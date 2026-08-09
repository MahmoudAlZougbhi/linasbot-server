/**
 * Content Managers hub section cards (plan screen map).
 * @typedef {object} CmSectionCard
 * @property {string} slug
 * @property {string | null} section API section id (null for publish hub)
 * @property {string} name
 * @property {string} description
 */

/** @type {CmSectionCard[]} */
export const CM_SECTION_CARDS = [
  {
    slug: "ai-basics",
    section: "ai_basics",
    name: "AI Basics",
    description: "Business identity, persona, and core AI grounding facts.",
  },
  {
    slug: "languages",
    section: "languages",
    name: "Languages",
    description: "Canonical language policy and Franco → Arabic response map.",
  },
  {
    slug: "style",
    section: "style",
    name: "Style & Tone",
    description: "Voice, tone, and writing guidelines for your AI.",
  },
  {
    slug: "dynamic-messages",
    section: "dynamic_messages",
    name: "Dynamic Messages",
    description: "Greeting and system message templates managed in CM.",
  },
  {
    slug: "services",
    section: "services",
    name: "Services",
    description: "Structured service/product catalog used by answers.",
  },
  {
    slug: "branches",
    section: "branches",
    name: "Locations",
    description: "Branches, stores, offices, hours, and availability (optional).",
  },
  {
    slug: "opening-hours",
    section: "opening_hours",
    name: "Opening Hours",
    description: "Named hour calendars (Men / Women / Branch) with Mon–Sun open or off.",
  },
  {
    slug: "prices",
    section: "prices",
    name: "Prices",
    description: "Catalog, base prices, discounts & packages — visual rules, no code.",
  },
  {
    slug: "care",
    section: "care",
    name: "Care / Instructions",
    description: "Preparation and aftercare or operational instructions tied to services.",
  },
  {
    slug: "knowledge",
    section: "knowledge",
    name: "Knowledge",
    description: "Narrative knowledge for retrieval after FAQ miss — educational articles only.",
  },
  {
    slug: "faq",
    section: "faq",
    name: "FAQ",
    description: "Linked 4-language Q&A — visual editor, no JSON. Canonical FAQ for production.",
  },
  {
    slug: "learning-inbox",
    section: null,
    name: "Learning Inbox",
    description: "Review unclear answers and add them into the canonical FAQ (same pipeline).",
  },
  {
    slug: "handoff",
    section: "handoff",
    name: "Human Handoff",
    description: "Handoff matrix and contact destinations (WhatsApp link, phone, email, URL).",
  },
  {
    slug: "restricted",
    section: "restricted",
    name: "Restricted / Unsupported",
    description: "Topics that must never be offered or handed off incorrectly.",
  },
  {
    slug: "actions",
    section: "actions",
    name: "Actions / Capabilities",
    description: "Enable or disable what the AI is allowed to do (DMs, comments, handoff, photo).",
  },
  {
    slug: "ai-limits",
    section: "ai_limits",
    name: "AI Limits",
    description: "Per-customer image and context usage limits for this business.",
  },
  {
    slug: "off-days",
    section: "off_days",
    name: "Off Days",
    description: "Weekly closed days and specific dates the AI should treat as closed.",
  },
  {
    slug: "sources",
    section: null,
    name: "Sources & Archive",
    description: "Inventory of migrated files, checksums, and restricted archives.",
  },
  {
    slug: "publish",
    section: null,
    name: "Preview / Validate / Publish",
    description: "Validate drafts, preview the answer packet, and publish for live customers.",
  },
];

/**
 * @param {string} slug
 * @returns {CmSectionCard | undefined}
 */
export function findCmSectionBySlug(slug) {
  return CM_SECTION_CARDS.find((card) => card.slug === slug);
}
