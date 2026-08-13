/**
 * Fails if known developer/internal phrases appear in production UI copy
 * (locale files + hardcoded screen strings under src/).
 *
 * Run: node --test mobile/linas-ai/tests/*.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const srcRoot = join(root, 'src');

/** Phrases that must never ship in production customer-facing copy. */
const BANNED = [
  'not wired',
  'not implemented',
  'set-plan',
  'test tenant',
  'test tenants',
  'test account',
  'entitlement mapping',
  'coming from backend',
  'fake iap',
  'no fake iap',
  'iap external',
  'server entitlements',
  'entitlements payload',
  'entitlements unavailable',
  'store iap',
  'after api deploy',
  'apis may not be deployed',
  'apis are live',
  'usage payload',
  'truthful metrics',
  'platform_owner role',
  'usermanagement permission',
  'livechat permission',
  'app a only',
  'change webhooks',
  'beta backend',
  'not ready for mobile login',
  'pull refresh after api',
  'voice upload failed (formdata)',
  'queued when provider',
  'no production video provider',
  'coming later — no production',
  'training (legacy)',
  'formation (legacy)',
  'التدريب (قديم)',
  'pas encore branché',
  'غير مفعّل في الإنتاج',
  'does not retrain an ai model',
  'admin set-plan',
  'in-app buy buttons are not wired',
  'purchase notifications map to entitlements',
];

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name === 'dist') continue;
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, out);
    else if (/\.(ts|tsx)$/.test(name)) out.push(p);
  }
  return out;
}

function productionUiCorpus() {
  const files = [
    ...walk(join(srcRoot, 'i18n')),
    ...walk(join(srcRoot, 'features')),
    ...walk(join(srcRoot, 'components')),
    ...walk(join(srcRoot, 'app')),
    join(root, 'App.tsx'),
  ].filter((p) => {
    // Keep API/helpers out of the user-copy scan when they are not screens.
    const rel = relative(root, p).replace(/\\/g, '/');
    if (rel.includes('/api/')) return false;
    if (rel.endsWith('Api.ts') || rel.endsWith('api.ts')) return false;
    return true;
  });

  const chunks = [];
  for (const file of files) {
    const text = readFileSync(file, 'utf8');
    // Ignore pure code comments that start with // or /* for __DEV__ blocks? Still scan full file —
    // banned phrases must not appear in any string literal that could render.
    chunks.push({ file: relative(root, file), text: text.toLowerCase() });
  }
  return chunks;
}

test('production UI copy has no known internal/developer phrases', () => {
  const corpus = productionUiCorpus();
  const hits = [];
  for (const { file, text } of corpus) {
    for (const phrase of BANNED) {
      if (text.includes(phrase.toLowerCase())) {
        hits.push(`${file}: "${phrase}"`);
      }
    }
  }
  assert.equal(
    hits.length,
    0,
    `Banned internal phrases found in production UI sources:\n${hits.join('\n')}`,
  );
});

test('subscription gate uses customer-facing title and description', () => {
  const en = readFileSync(join(srcRoot, 'i18n/locales/en.ts'), 'utf8');
  const gate = readFileSync(join(srcRoot, 'features/billing/SubscriptionGateScreen.tsx'), 'utf8');
  assert.match(en, /subscribeGateTitle:\s*'Subscribe to continue'/);
  assert.match(
    en,
    /Choose a plan to unlock your AI assistant, AI Setup, and social media integrations\. Guest mode remains available without a subscription\./,
  );
  assert.match(gate, /tr\('subscribeGateTitle'\)/);
  assert.match(gate, /tr\('subscribeGateBody'\)/);
  assert.doesNotMatch(gate, /\bnote\?:/);
  assert.doesNotMatch(gate, /\{note \?/);
  assert.doesNotMatch(en, /set-plan|not wired|test tenant/i);
});

test('AR and FR subscription gate strings exist', () => {
  const ar = readFileSync(join(srcRoot, 'i18n/locales/ar.ts'), 'utf8');
  const fr = readFileSync(join(srcRoot, 'i18n/locales/fr.ts'), 'utf8');
  assert.match(ar, /subscribeGateTitle:/);
  assert.match(ar, /subscribeGateBody:/);
  assert.match(fr, /subscribeGateTitle:/);
  assert.match(fr, /subscribeGateBody:/);
});

test('raw entitlement/usage JSON dumps are __DEV__ gated', () => {
  const billing = readFileSync(join(srcRoot, 'features/billing/BillingScreen.tsx'), 'utf8');
  const dashboard = readFileSync(join(srcRoot, 'features/dashboard/DashboardScreen.tsx'), 'utf8');
  const simple = readFileSync(join(srcRoot, 'features/shared/SimpleResourceScreen.tsx'), 'utf8');
  for (const [name, text] of [
    ['BillingScreen', billing],
    ['DashboardScreen', dashboard],
    ['SimpleResourceScreen', simple],
  ]) {
    if (text.includes('JSON.stringify')) {
      assert.match(text, /__DEV__/, `${name} must gate JSON.stringify behind __DEV__`);
    }
  }
});

test('tenant Dashboard has no Platform Owner metrics stub', () => {
  const dashboard = readFileSync(join(srcRoot, 'features/dashboard/DashboardScreen.tsx'), 'utf8');
  assert.doesNotMatch(dashboard, /Platform metrics|Owner only|Owner access only|isPlatformOwner|\/api\/platform\/metrics/);
  assert.doesNotMatch(dashboard, /\bReady\b/);
  assert.doesNotMatch(dashboard, /0 \/ —/);
  assert.match(dashboard, /\/api\/mobile\/dashboard|useTenantDashboard|GrowthPlanCard/);
});
