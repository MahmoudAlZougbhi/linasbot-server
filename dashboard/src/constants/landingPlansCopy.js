/** Marketing copy for landing pricing cards. Prices always come from /api/public/plans. */
export const PLAN_LANDING_COPY = {
  lite: {
    tier: 'SOLO',
    blurb: 'For solo businesses with light daily message volume.',
    included: ['Instagram & Facebook messages', '50 saved Smart Answers', '1 owner account'],
    missing: 'No comments, WhatsApp or TikTok',
  },
  starter: {
    tier: 'SMALL BUSINESS',
    blurb: 'For small businesses adding comments and WhatsApp.',
    included: [
      'Instagram & Facebook messages + comments',
      'WhatsApp messages',
      '110 saved Smart Answers',
      'Owner + 2 team members',
    ],
    missing: 'TikTok not included',
  },
  growth: {
    tier: 'GROWING BUSINESS',
    blurb: 'For growing businesses active across every channel.',
    included: ['All channels included', 'Messages + comments', '250 saved Smart Answers', 'Owner + 5 team members'],
    missing: null,
    recommended: true,
  },
  pro: {
    tier: 'HIGH VOLUME',
    blurb: 'For busy teams handling high customer volume.',
    included: ['All channels included', 'Messages + comments', '600 saved Smart Answers', 'Unlimited team members'],
    missing: null,
  },
  max: {
    tier: 'MAXIMUM SCALE',
    blurb: 'For established businesses needing maximum AI capacity.',
    included: ['All channels included', 'Messages + comments', '1,500 saved Smart Answers', 'Unlimited team members'],
    missing: null,
  },
};
