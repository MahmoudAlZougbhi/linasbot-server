/** Marketing copy for landing pricing cards. Numeric quotas come from /api/public/plans. */
export const LITE_INCLUDED_MESSAGES = 550;
export const PLAN_LANDING_COPY = {
  lite: {
    tier: 'SOLO',
    blurb: 'For solo businesses with light daily message volume.',
    included: ['Instagram & Facebook messages', 'Saved Smart Answers', 'Owner account'],
    missing: 'No comments, WhatsApp or TikTok',
  },
  starter: {
    tier: 'SMALL BUSINESS',
    blurb: 'For small businesses adding comments and WhatsApp.',
    included: [
      'Instagram & Facebook messages + comments',
      'WhatsApp messages',
      'Saved Smart Answers',
      'Owner plus additional seats',
    ],
    missing: 'TikTok not included',
  },
  growth: {
    tier: 'GROWING BUSINESS',
    blurb: 'For growing businesses active across every channel.',
    included: ['All channels included', 'Messages + comments', 'Saved Smart Answers', 'Team seats'],
    missing: null,
    recommended: true,
  },
  pro: {
    tier: 'HIGH VOLUME',
    blurb: 'For busy teams handling high customer volume.',
    included: ['All channels included', 'Messages + comments', 'Saved Smart Answers', 'Unlimited team members'],
    missing: null,
  },
  max: {
    tier: 'MAXIMUM SCALE',
    blurb: 'For established businesses needing maximum AI capacity.',
    included: ['All channels included', 'Messages + comments', 'Saved Smart Answers', 'Unlimited team members'],
    missing: null,
  },
};
