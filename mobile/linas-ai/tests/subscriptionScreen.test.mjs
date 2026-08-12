/**
 * Subscription screen + frozen plan catalog mobile contracts.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const srcRoot = join(root, 'src');
const read = (rel) => readFileSync(join(srcRoot, rel), 'utf8');

const PLAN_ORDER = ['lite', 'starter', 'growth', 'pro', 'max'];
const FROZEN = {
  lite: { price: 9.99, credits: 7000, faq: 50, seats: 0, comments: false },
  starter: { price: 25, credits: 17500, faq: 110, seats: 2, comments: true },
  growth: { price: 59, credits: 41300, faq: 250, seats: 5, comments: true },
  pro: { price: 109, credits: 76300, faq: 600, seats: null, comments: true },
  max: { price: 259, credits: 181300, faq: 1500, seats: null, comments: true },
};

function planRank(id) {
  return PLAN_ORDER.indexOf(id);
}

function resolvePlanCta(target, currentPlan, status, { storePriceAvailable, purchasePending }) {
  if (purchasePending) return { kind: 'disabled', enabled: false };
  const paid = ['active', 'trial', 'grace', 'canceled'].includes(String(status || '').toLowerCase()) && currentPlan;
  if (paid && currentPlan === target) return { kind: 'current', enabled: false };
  if (!storePriceAvailable) return { kind: 'disabled', enabled: false };
  if (!paid || !currentPlan) return { kind: 'choose', enabled: true };
  if (planRank(target) > planRank(currentPlan)) return { kind: 'upgrade', enabled: true };
  return { kind: 'switch_renewal', enabled: true };
}

test('planCatalog.ts encodes frozen five-plan matrix', () => {
  const src = read('features/billing/planCatalog.ts');
  for (const id of PLAN_ORDER) {
    assert.match(src, new RegExp(`${id}:`));
    const row = FROZEN[id];
    assert.match(src, new RegExp(`includedCredits:\\s*${row.credits}`));
    assert.match(src, new RegExp(`faqCapacity:\\s*${row.faq}`));
  }
  assert.match(src, /catalogPriceUsd:\s*9\.99/);
  assert.match(src, /catalogPriceUsd:\s*25/);
  assert.match(src, /catalogPriceUsd:\s*59/);
  assert.match(src, /catalogPriceUsd:\s*109/);
  assert.match(src, /catalogPriceUsd:\s*259/);
  assert.match(src, /additionalSeats:\s*null/);
  assert.match(src, /commentAutomation:\s*false/);
  assert.match(src, /recommended:\s*true/);
});

test('common features keys cover agreed product list', () => {
  const src = read('features/billing/planCatalog.ts');
  for (const key of [
    'subCommonOwnerCopilot',
    'subCommonContentManagement',
    'subCommonAiReplies',
    'subCommonIgDm',
    'subCommonFbDm',
    'subCommonAnalytics',
    'subCommonIntegrations',
  ]) {
    assert.match(src, new RegExp(key));
  }
});

test('CTA states: none / current / upgrade / downgrade / unavailable', () => {
  assert.equal(resolvePlanCta('growth', null, 'none', { storePriceAvailable: true, purchasePending: false }).kind, 'choose');
  assert.equal(resolvePlanCta('growth', 'growth', 'active', { storePriceAvailable: true, purchasePending: false }).kind, 'current');
  assert.equal(resolvePlanCta('pro', 'starter', 'active', { storePriceAvailable: true, purchasePending: false }).kind, 'upgrade');
  assert.equal(resolvePlanCta('lite', 'max', 'active', { storePriceAvailable: true, purchasePending: false }).kind, 'switch_renewal');
  assert.equal(resolvePlanCta('lite', null, 'none', { storePriceAvailable: false, purchasePending: false }).enabled, false);
});

test('storePricing keeps preview unavailable and loads via IAP module', () => {
  const src = read('features/billing/storePricing.ts');
  assert.match(src, /available:\s*false/);
  assert.match(src, /store_unavailable|native_iap_unavailable/);
  assert.match(src, /preview:\s*true/);
  assert.match(src, /displayPrice/);
  assert.match(src, /loadIapModule/);
});

test('BillingScreen supports monthly/yearly toggle + Apple IAP actions', () => {
  const billing = read('features/billing/BillingScreen.tsx');
  assert.match(billing, /BillingPeriodToggle/);
  assert.match(billing, /yearly|BillingPeriod/);
  assert.match(billing, /CommonFeaturesCard/);
  assert.match(billing, /subCreditsExplain/);
  assert.match(billing, /PlanCardView/);
  assert.match(billing, /restorePurchases|onRestore/);
  const card = read('features/billing/PlanCardView.tsx');
  assert.match(card, /subPriceUnavailable/);
  assert.match(card, /subPerYear|period/);
});

test('exact EN plan copy present in locale table', () => {
  const en = read('i18n/locales/subscriptionEn.ts') + read('i18n/locales/en.ts');
  for (const phrase of [
    'Essential AI replies for a solo business.',
    '7,000 AI credits every billing month',
    'Comment automation is not included',
    'Add comment automation and a small team.',
    '17,500 AI credits every billing month',
    'Owner + 2 additional members',
    'More capacity for a growing business.',
    '41,300 AI credits every billing month',
    'Owner + 5 additional members',
    'High-volume AI automation for growing teams.',
    '76,300 AI credits every billing month',
    'Unlimited additional members',
    'Maximum monthly AI capacity for busy businesses.',
    '181,300 AI credits every billing month',
    'Up to 1,500 saved FAQ pairs',
    'Included in every plan',
    'Linas AI Owner Copilot',
    'Content Management',
    'Instagram DM automation',
    'Facebook DM automation',
    'Analytics and usage insights',
  ]) {
    assert.match(en, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
  assert.doesNotMatch(en, /Higher credits/);
  assert.doesNotMatch(en, /Creative Studio/);
  assert.doesNotMatch(en, /OpenAI/);
  assert.doesNotMatch(en, /sub\w+.*profit/i);
  const subBlock = read('i18n/locales/subscriptionEn.ts');
  assert.doesNotMatch(subBlock, /\bCM\b/);
  assert.doesNotMatch(subBlock, /Higher credits/);
});

test('Arabic subscription strings exist with exact credit numbers', () => {
  const ar = read('i18n/locales/subscriptionAr.ts');
  assert.match(ar, /subLiteFeatCredits:/);
  assert.match(ar, /7,000/);
  assert.match(ar, /17,500/);
  assert.match(ar, /41,300/);
  assert.match(ar, /76,300/);
  assert.match(ar, /181,300/);
  assert.match(ar, /subCommonTitle:/);
  assert.match(ar, /subCtaSwitchLite:/);
});

test('subscriptionCta.ts mirrors CTA kinds used by screen', () => {
  const src = read('features/billing/subscriptionCta.ts');
  for (const kind of ['choose', 'upgrade', 'current', 'switch_renewal', 'disabled']) {
    assert.match(src, new RegExp(`'${kind}'`));
  }
  assert.match(src, /subCtaSwitchLite/);
  assert.match(src, /subCtaUpgradeMax/);
});

test('no provider cost / profit strings in billing sources', () => {
  for (const rel of [
    'features/billing/BillingScreen.tsx',
    'features/billing/planCatalog.ts',
    'features/billing/PlanCardView.tsx',
    'features/billing/storePricing.ts',
  ]) {
    const text = read(rel).toLowerCase();
    assert.equal(text.includes('openai'), false, rel);
    assert.equal(text.includes('provider cost'), false, rel);
    assert.equal(text.includes('profit'), false, rel);
  }
});
