/** Fixed list prices from services/plan_economics.py — do not invent IAP purchase UI. */
export type PlanId = 'starter' | 'growth' | 'pro' | 'max';

export type PlanCard = {
  id: PlanId;
  name: string;
  priceMonthly: number;
  blurb: string;
  features: string[];
};

export const PLAN_CARDS: PlanCard[] = [
  {
    id: 'starter',
    name: 'Starter',
    priceMonthly: 24.99,
    blurb: 'Owner assistant, CM, customer DM automation',
    features: ['Owner assistant', 'Content Management', 'Customer DM automation', 'FAQ (Smart Answers)'],
  },
  {
    id: 'growth',
    name: 'Growth',
    priceMonthly: 59,
    blurb: 'Starter + comment automation',
    features: ['Everything in Starter', 'Comment automation'],
  },
  {
    id: 'pro',
    name: 'Pro',
    priceMonthly: 109,
    blurb: 'Creative Studio, scheduling, image & video',
    features: ['Everything in Growth', 'Creative Studio', 'Scheduling', 'Image & video gen'],
  },
  {
    id: 'max',
    name: 'Max',
    priceMonthly: 250,
    blurb: 'Highest tier + advanced capabilities',
    features: ['Everything in Pro', 'Advanced capabilities'],
  },
];

export function formatUsd(amount: number): string {
  return amount % 1 === 0 ? `$${amount}` : `$${amount.toFixed(2)}`;
}
