import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');

function read(rel) {
  return readFileSync(join(root, rel), 'utf8');
}

test('resolveWebPlanAllowed prefers API flag then entitlements fallback', () => {
  const src = read('features/integrations/webChatPlanAccess.ts');
  assert.match(src, /membership_allows === true/);
  assert.match(src, /membership_allows === false/);
  assert.match(src, /entitlementFallback === true/);
  assert.match(src, /subscription_exempt === true/);
  assert.match(src, /PLAN_CATALOG\[planId\]\.web/);
});

test('WebChatCard uses unified webPlanAllowed for banner and enable', () => {
  const src = read('features/integrations/WebChatCard.tsx');
  assert.match(src, /resolveWebPlanAllowed/);
  assert.match(src, /const planBlocked = !webPlanAllowed/);
  assert.doesNotMatch(src, /membership_allows === false/);
  assert.doesNotMatch(src, /!settings\?\.membership_allows/);
});

test('max plan catalog includes website chat', () => {
  const catalog = read('features/billing/planCatalog.ts');
  assert.match(catalog, /max:[\s\S]*?web:\s*true/);
  assert.match(catalog, /starter:[\s\S]*?web:\s*true/);
  assert.match(catalog, /lite:[\s\S]*?web:\s*false/);
});
