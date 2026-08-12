/**
 * Apple product id mapping + store pricing helper contracts.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (rel) => readFileSync(join(root, 'src', rel), 'utf8');

const PLAN_ORDER = ['lite', 'starter', 'growth', 'pro', 'max'];
const ASC = {
  lite: 'basic',
  starter: 'plus',
  growth: 'growth',
  pro: 'pro',
  max: 'scale',
};
const CREDIT_PACKS = [2500, 5000, 12500, 25000, 50000];

test('appleProductIds maps Linas plan_ids to ASC SKUs', () => {
  const src = read('features/billing/appleProductIds.ts');
  for (const plan of PLAN_ORDER) {
    const sku = ASC[plan];
    assert.match(src, new RegExp(`com\\.linasai\\.subscription\\.${sku}\\.monthly`));
    assert.match(src, new RegExp(`com\\.linasai\\.subscription\\.${sku}\\.yearly`));
  }
  for (const n of CREDIT_PACKS) {
    assert.match(src, new RegExp(`com\\.linasai\\.credits\\.${n}`));
  }
  assert.match(src, /appleProductIdForPlan/);
  assert.match(src, /planIdForAppleProduct/);
  assert.match(src, /periodForAppleProduct/);
  assert.match(src, /creditAmountForAppleProduct/);
});

test('planCatalog appleProductId uses canonical monthly ASC SKUs', () => {
  const src = read('features/billing/planCatalog.ts');
  assert.match(src, /com\.linasai\.subscription\.basic\.monthly/);
  assert.match(src, /com\.linasai\.subscription\.plus\.monthly/);
  assert.match(src, /com\.linasai\.subscription\.growth\.monthly/);
  assert.match(src, /com\.linasai\.subscription\.pro\.monthly/);
  assert.match(src, /com\.linasai\.subscription\.scale\.monthly/);
  assert.doesNotMatch(src, /com\.linasai\.app\.lite\.monthly/);
});

test('storePricing never uses catalog USD as available checkout price', () => {
  const src = read('features/billing/storePricing.ts');
  assert.match(src, /displayPrice/);
  assert.match(src, /native_iap_unavailable/);
  assert.match(src, /previewCatalogPrices/);
  assert.match(src, /available:\s*false/);
  // preview helper must keep available:false
  const previewBlock = src.slice(src.indexOf('previewCatalogPrices'));
  assert.match(previewBlock, /available:\s*false/);
  assert.match(previewBlock, /preview:\s*true/);
  assert.doesNotMatch(src, /expo-in-app-purchases/);
});

test('iapPurchases verifies before finishTransaction', () => {
  const src = read('features/billing/iapPurchases.ts');
  assert.match(src, /\/api\/entitlements\/apple\/verify/);
  assert.match(src, /\/api\/entitlements\/apple\/restore/);
  assert.match(src, /\/api\/entitlements\/apple\/app-account-token/);
  assert.match(src, /finishTransaction/);
  assert.match(src, /beginRefundRequestIOS/);
  assert.match(src, /apps\.apple\.com\/account\/subscriptions/);
  const verifyIdx = src.indexOf('verifyOnServer');
  const finishIdx = src.indexOf('finishTransaction({ purchase');
  assert.ok(verifyIdx > 0 && finishIdx > verifyIdx, 'finish after verify helper usage');
});

test('BillingScreen wires period toggle + Apple IAP copy', () => {
  const billing = read('features/billing/BillingScreen.tsx');
  assert.match(billing, /BillingPeriodToggle/);
  assert.match(billing, /CreditPacksSection/);
  assert.match(billing, /purchaseSubscription/);
  assert.match(billing, /restorePurchases/);
  assert.match(billing, /openManageSubscriptions/);
  assert.doesNotMatch(billing, /Apple Pay/);
  const en = read('i18n/locales/subscriptionEn.ts');
  assert.match(en, /Apple In-App Purchase/);
  assert.doesNotMatch(en, /Apple Pay/);
});
