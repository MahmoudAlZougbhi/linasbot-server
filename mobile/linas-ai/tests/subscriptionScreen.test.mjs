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
  lite: { price: 10, messages: 550, credits: 7000, faq: 50, seats: 0, comments: false },
  starter: { price: 29, messages: 1200, credits: 17500, faq: 110, seats: 2, comments: true },
  growth: { price: 59, messages: 3000, credits: 41300, faq: 250, seats: 5, comments: true },
  pro: { price: 120, messages: 10000, credits: 76300, faq: 600, seats: null, comments: true },
  max: { price: 279, messages: 25000, credits: 181300, faq: 1500, seats: null, comments: true },
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

test('planCatalog.ts encodes frozen five-plan matrix with channel flags', () => {
  const src = read('features/billing/planCatalog.ts');
  for (const id of PLAN_ORDER) {
    assert.match(src, new RegExp(`${id}:`));
    const row = FROZEN[id];
    assert.match(src, new RegExp(`includedCredits:\\s*${row.credits}`));
    assert.match(src, new RegExp(`includedMessages:\\s*${row.messages}`));
    assert.match(src, new RegExp(`faqCapacity:\\s*${row.faq}`));
  }
  assert.match(src, /catalogPriceUsd:\s*10/);
  assert.match(src, /catalogPriceUsd:\s*29/);
  assert.match(src, /catalogPriceUsd:\s*59/);
  assert.match(src, /catalogPriceUsd:\s*120/);
  assert.match(src, /catalogPriceUsd:\s*279/);
  assert.match(src, /additionalSeats:\s*null/);
  assert.match(src, /commentAutomation:\s*false/);
  assert.match(src, /whatsapp:\s*false/);
  assert.match(src, /tiktok:\s*true/);
  assert.match(src, /recommended:\s*true/);
  assert.match(src, /typeof row.comment_automation === 'boolean'/);
  assert.match(src, /typeof row.whatsapp === 'boolean'/);
  assert.match(src, /typeof row.web === 'boolean'/);
  assert.match(src, /typeof row.tiktok === 'boolean'/);
  assert.match(src, /additional_seats === null/);
  assert.match(src, /additional_seats_unlimited === true/);
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

test('BillingScreen downgrade flow wires confirm sheet and pending banner', () => {
  const billing = read('features/billing/BillingScreen.tsx');
  assert.match(billing, /DowngradeConfirmSheet/);
  assert.match(billing, /subDowngradeScheduled/);
  assert.match(billing, /cancelPendingDowngrade/);
  assert.match(billing, /browseMode === 'downgrade'/);
  const current = read('features/billing/CurrentPlanScreen.tsx');
  assert.match(current, /PendingDowngradeBanner/);
  assert.match(current, /subDowngradePlan/);
});

test('planChangeApi calls schedule-downgrade and pending-plan-change endpoints', () => {
  const src = read('features/billing/planChangeApi.ts');
  assert.match(src, /\/api\/entitlements\/schedule-downgrade/);
  assert.match(src, /\/api\/entitlements\/pending-plan-change/);
});

test('BillingScreen routes no-sub to choose, has-sub to current, upgrade + credits', () => {
  const billing = read('features/billing/BillingScreen.tsx');
  assert.match(billing, /CurrentPlanScreen/);
  assert.match(billing, /ChoosePlanScreen/);
  assert.match(billing, /BuyCreditsSheet/);
  assert.match(billing, /creditsOpen && !entitlement.messageBillingActive/);
  const flow = read('features/billing/useBuyCreditsFlow.ts');
  assert.match(flow, /if \(next && messageBillingActive\) return/);
  assert.match(billing, /hasSub/);
  assert.match(billing, /setBrowsePlans\(true\)/);
  assert.match(billing, /purchaseSubscription/);
  assert.match(billing, /purchaseCredits/);
  assert.match(billing, /onBack/);
  assert.match(billing, /setBrowsePlans\(false\)/);
  assert.doesNotMatch(billing, /nav\.goChat\(\)/);
  assert.doesNotMatch(billing, /view === 'choose' \?/);
  assert.match(billing, /useState\(openChoosePlan\)/);
  assert.match(billing, /showChooseChrome/);
  assert.match(billing, /entitlement\.loading/);
  const choose = read('features/billing/ChoosePlanScreen.tsx');
  assert.match(choose, /BillingPeriodToggle/);
  assert.match(choose, /PlanChipRow/);
  assert.match(choose, /subYourPlan/);
  const current = read('features/billing/CurrentPlanScreen.tsx');
  assert.match(current, /subUpgradePlan/);
  assert.match(current, /onBuyCredits/);
  assert.match(current, /messageBillingActive/);
  assert.match(current, /subMessagesPending/);
  assert.doesNotMatch(current, /membershipLabel=\{plan\.includedMessages/);
  assert.doesNotMatch(current, /includedMessages \?\? plan\.includedMessages/);
});

test('exact EN plan copy present in locale table', () => {
  const en = read('i18n/locales/subscriptionEn.ts') + read('i18n/locales/en.ts');
  for (const phrase of [
    'Best for solo businesses with a light daily message volume.',
    'Best for small businesses adding comments and WhatsApp.',
    'Best for busy businesses handling high daily message volume.',
    'Best for large businesses with the highest AI reply volume.',
    'Instagram & Facebook DMs',
    'Instagram & Facebook DMs + comments',
    'WhatsApp messages',
    'TikTok DMs + comments',
    '{n} saved Smart Q&A',
    '1 owner account',
    '{n} additional team members',
    'Unlimited team members',
    'Choose a plan',
    'Your current plan',
    'Upgrade plan',
    'Downgrade plan',
    'Schedule downgrade',
    'Cancel downgrade',
    'Add messages',
    'Choose a message pack',
    'Leftover credit packs',
    'Buy leftover credits',
    'They are not AI messages',
    'Purchased messages do not expire.',
    'SOLO BUSINESS',
    'SMALL BUSINESS',
    'HIGH VOLUME',
    'MAXIMUM CAPACITY',
    'Smart Q&A uses 0 messages',
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

test('Arabic subscription strings exist with exact message numbers', () => {
  const ar = read('i18n/locales/subscriptionAr.ts');
  assert.match(ar, /subLiteFeatCredits:/);
  assert.match(ar, /550/);
  assert.match(ar, /1,200/);
  assert.match(ar, /3,000/);
  assert.match(ar, /10,000/);
  assert.match(ar, /25,000/);
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
    'features/billing/planEntitlements.ts',
    'features/billing/PlanDetailCard.tsx',
    'features/billing/storePricing.ts',
  ]) {
    const text = read(rel).toLowerCase();
    assert.equal(text.includes('openai'), false, rel);
    assert.equal(text.includes('provider cost'), false, rel);
    assert.equal(text.includes('profit'), false, rel);
  }
});

test('planEntitlements maps included/not-included from catalog flags', () => {
  const src = read('features/billing/planEntitlements.ts');
  const catalog = read('features/billing/planCatalog.ts');
  assert.match(src, /plan\.commentAutomation/);
  assert.match(src, /plan\.whatsapp/);
  assert.match(src, /plan\.tiktok/);
  assert.match(src, /plan\.faqCapacity/);
  assert.match(src, /plan\.additionalSeats/);
  assert.match(src, /subFeatDmOnly/);
  assert.match(src, /subFeatDmComments/);
  assert.match(src, /subFeatWhatsApp/);
  assert.match(src, /subFeatTikTok/);
  assert.match(src, /excluded\.push\('comments'\)/);
  assert.match(src, /excluded\.push\('whatsapp'\)/);
  assert.match(src, /excluded\.push\('tiktok'\)/);
  assert.match(catalog, /lite:[\s\S]*?whatsapp:\s*false[\s\S]*?tiktok:\s*false/);
  assert.match(catalog, /starter:[\s\S]*?whatsapp:\s*true[\s\S]*?tiktok:\s*false/);
  assert.match(catalog, /growth:[\s\S]*?whatsapp:\s*true[\s\S]*?tiktok:\s*true/);
  assert.match(catalog, /pro:[\s\S]*?whatsapp:\s*true[\s\S]*?tiktok:\s*true/);
  assert.match(catalog, /max:[\s\S]*?whatsapp:\s*true[\s\S]*?tiktok:\s*true/);
});

test('planColors defines distinct premium palette per tier', () => {
  const src = read('features/billing/planColors.ts');
  for (const id of PLAN_ORDER) {
    assert.match(src, new RegExp(`${id}:`));
  }
  assert.match(src, /accentForPlan/);
  assert.match(src, /planNameColor/);
  assert.doesNotMatch(src, /nameOnForest/);
  assert.match(src, /lite:[\s\S]*?#64748B/);
  assert.match(src, /starter:[\s\S]*?#008B8B/);
  assert.match(src, /growth:[\s\S]*?#059669/);
  assert.match(src, /pro:[\s\S]*?#6366F1/);
  assert.match(src, /max:[\s\S]*?#D97706/);
});

test('billing surfaces tint plan names from planColors', () => {
  for (const [file, pattern] of [
    ['features/billing/PlanCardView.tsx', /planNameColor/],
    ['features/billing/PlanDetailCard.tsx', /planNameColor/],
    ['features/billing/PlanChipRow.tsx', /planNameColor/],
    ['features/billing/CurrentPlanHeroCard.tsx', /planNameColor/],
    ['features/billing/CurrentPlanSummary.tsx', /planNameColor/],
    ['features/billing/ChoosePlanScreen.tsx', /accentForPlan/],
    ['features/dashboard/sections/GrowthPlanCard.tsx', /planNameColor/],
  ]) {
    assert.match(read(file), pattern, file);
  }
  assert.match(read('features/billing/subscriptionCta.ts'), /export \{ accentForPlan \} from '\.\/planColors'/);
});

test('GrowthPlanCard uses ledger remaining, not catalog allowance, for membership', () => {
  const src = read('features/dashboard/sections/GrowthPlanCard.tsx');
  assert.match(src, /included_remaining/);
  assert.match(src, /granted_messages/);
  assert.match(src, /used_messages/);
  assert.match(src, /usage_progress_ratio/);
  assert.match(src, /billingActive \? formatCount\(membership\) : '—'/);
  assert.doesNotMatch(src, /membership = billingActive \? Number\(plan.included_remaining \?\? 0\) : included/);
  assert.doesNotMatch(src, /limit - available/);
});

test('live credit IAP is leftover credits, not a 1:1 message relabel', () => {
  const en = read('i18n/locales/subscriptionEn.ts');
  const sheet = read('features/billing/BuyCreditsSheet.tsx');
  const packs = read('features/billing/CreditPacksSection.tsx');
  const hero = read('features/billing/CurrentPlanHeroCard.tsx');
  assert.match(en, /leftover credits/);
  assert.match(en, /They are not AI messages/);
  assert.match(sheet, /subCreditsUnit/);
  assert.match(sheet, /subBuyCreditsCta/);
  assert.match(packs, /subCreditsPacksTitle/);
  assert.match(hero, /subBuyCredits/);
  assert.match(hero, /messageBillingActive \? null/);
  assert.match(sheet, /subCreditsPacksTitle/);
  assert.match(sheet, /subLeftoverNoExpire/);
  assert.doesNotMatch(sheet, /subPurchasedNoExpire/);
  assert.doesNotMatch(sheet, /messageBillingActive \? tr\('subAddMessages'\)/);
  assert.doesNotMatch(en, /subCreditsUnit:\s*'messages'/);
  assert.doesNotMatch(sheet, /2500[\s\S]{0,40}messages/);
});

test('CurrentPlanSummary never copies leftover credits as messages', () => {
  const src = read('features/billing/CurrentPlanSummary.tsx');
  assert.match(src, /messageBillingActive/);
  assert.match(src, /includedMessages/);
  assert.match(src, /includedRemaining/);
  assert.match(src, /subIncludedEachMonth/);
  assert.match(src, /subIncludedRemaining/);
  assert.match(src, /subMessagesPending/);
  assert.match(src, /subLeftoverCredits/);
  assert.match(src, /creditBalance/);
  assert.doesNotMatch(src, /subIncludedRemaining[\s\S]{0,80}includedMessages/);
  assert.doesNotMatch(src, /subTotalAvailable[\s\S]{0,80}creditBalance/);
});
