/** Plan cards mirror server catalog — prefer /api/public/plans at runtime. */
export type PlanId = 'lite' | 'starter' | 'growth' | 'pro' | 'max';

export type PlanCard = {
  id: PlanId;
  name: string;
  priceMonthly: number;
  blurb: string;
  features: string[];
  includedCredits: number;
  faqCapacity: number;
  additionalSeats: number | null;
  commentAutomation: boolean;
};

/** Frozen membership-v1 matrix (must match services.membership.plan_catalog). */
export const PLAN_CARDS: PlanCard[] = [
  {
    id: 'lite',
    name: 'Lite',
    priceMonthly: 9.99,
    blurb: 'Owner assistant, AI Setup, DM automation — comments disabled',
    features: ['Owner assistant', 'AI Setup', 'Customer DM automation', 'FAQ (50)'],
    includedCredits: 7000,
    faqCapacity: 50,
    additionalSeats: 0,
    commentAutomation: false,
  },
  {
    id: 'starter',
    name: 'Starter',
    priceMonthly: 25,
    blurb: 'Lite + comment automation + 2 seats',
    features: ['Everything in Lite', 'Comment automation', '2 additional seats', 'FAQ (110)'],
    includedCredits: 17500,
    faqCapacity: 110,
    additionalSeats: 2,
    commentAutomation: true,
  },
  {
    id: 'growth',
    name: 'Growth',
    priceMonthly: 59,
    blurb: 'Higher credits, 5 seats, FAQ 250',
    features: ['Everything in Starter', '5 additional seats', 'FAQ (250)'],
    includedCredits: 41300,
    faqCapacity: 250,
    additionalSeats: 5,
    commentAutomation: true,
  },
  {
    id: 'pro',
    name: 'Pro',
    priceMonthly: 109,
    blurb: 'Creative Studio, scheduling, unlimited seats',
    features: ['Everything in Growth', 'Creative Studio', 'Scheduling', 'Unlimited seats', 'FAQ (600)'],
    includedCredits: 76300,
    faqCapacity: 600,
    additionalSeats: null,
    commentAutomation: true,
  },
  {
    id: 'max',
    name: 'Max',
    priceMonthly: 259,
    blurb: 'Highest included credits + advanced capabilities',
    features: ['Everything in Pro', 'Advanced capabilities', 'FAQ (1500)'],
    includedCredits: 181300,
    faqCapacity: 1500,
    additionalSeats: null,
    commentAutomation: true,
  },
];

export function formatUsd(amount: number): string {
  return amount % 1 === 0 ? `$${amount}` : `$${amount.toFixed(2)}`;
}
