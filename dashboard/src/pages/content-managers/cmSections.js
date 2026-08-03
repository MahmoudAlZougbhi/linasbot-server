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
    description: "Clinic identity, persona, and core AI grounding facts.",
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
    description: "Voice, tone, and writing guidelines for Linas AI.",
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
    description: "Structured service catalog used by answers and booking.",
  },
  {
    slug: "branches",
    section: "branches",
    name: "Branches & Hours",
    description: "Locations, hours, and branch-level availability.",
  },
  {
    slug: "prices",
    section: "prices",
    name: "Prices",
    description: "Exact price rows — structured source of truth for amounts.",
  },
  {
    slug: "care",
    section: "care",
    name: "Preparation & Aftercare",
    description: "Pre- and post-care guidance tied to services.",
  },
  {
    slug: "knowledge",
    section: "knowledge",
    name: "Knowledge",
    description: "Narrative knowledge chunks for retrieval after FAQ miss.",
  },
  {
    slug: "faq",
    section: "faq",
    name: "FAQ",
    description: "Exact FAQ pairs with 4-language auto-translate preserved.",
  },
  {
    slug: "handoff",
    section: "handoff",
    name: "Booking & Human Handoff",
    description: "Handoff matrix and WhatsApp numbers (draft authoring).",
  },
  {
    slug: "restricted",
    section: "restricted",
    name: "Restricted / Unsupported",
    description: "Topics that must never route to booking or WhatsApp handoff.",
  },
  {
    slug: "publish",
    section: null,
    name: "Preview / Validate / Publish",
    description: "Validate drafts, preview for Testing Lab, and publish when enabled.",
  },
];

/**
 * @param {string} slug
 * @returns {CmSectionCard | undefined}
 */
export function findCmSectionBySlug(slug) {
  return CM_SECTION_CARDS.find((card) => card.slug === slug);
}
