import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');

function read(rel) {
  return readFileSync(join(root, rel), 'utf8');
}

/** Keep in sync with resolveWebPlanAllowed in webChatPlanAccess.ts */
function resolveWebPlanAllowed(settings, entitlementFallback) {
  if (entitlementFallback === true || settings?.membership_allows === true) return true;
  if (entitlementFallback === false || settings?.membership_allows === false) return false;
  return false;
}

test('resolveWebPlanAllowed prefers API flag then entitlements fallback', () => {
  const src = read('features/integrations/webChatPlanAccess.ts');
  assert.match(src, /membership_allows === true/);
  assert.match(src, /membership_allows === false/);
  assert.match(src, /entitlementFallback === true/);
  assert.match(src, /subscription_exempt === true/);
  assert.match(src, /PLAN_CATALOG\[planId\]\.web/);
  assert.match(src, /trim\(\)\.toLowerCase\(\)/);
});

test('resolveWebPlanAllowed allows when entitlements grant despite stale membership_allows', () => {
  assert.equal(resolveWebPlanAllowed({ membership_allows: false }, true), true);
  assert.equal(resolveWebPlanAllowed({ membership_allows: true }, false), true);
  assert.equal(resolveWebPlanAllowed({ membership_allows: false }, false), false);
  assert.equal(resolveWebPlanAllowed(null, null), false);
  assert.equal(resolveWebPlanAllowed({ membership_allows: undefined }, true), true);
});

test('WebChatCard uses unified webPlanAllowed for banner and enable', () => {
  const src = read('features/integrations/WebChatCard.tsx');
  assert.match(src, /resolveWebPlanAllowed/);
  assert.match(src, /const planBlocked = !loading && !webPlanAllowed/);
  assert.doesNotMatch(src, /membership_allows === false/);
  assert.doesNotMatch(src, /!settings\?\.membership_allows/);
});

test('max plan catalog includes website chat', () => {
  const catalog = read('features/billing/planCatalog.ts');
  assert.match(catalog, /max:[\s\S]*?web:\s*true/);
  assert.match(catalog, /starter:[\s\S]*?web:\s*true/);
  assert.match(catalog, /lite:[\s\S]*?web:\s*false/);
});
