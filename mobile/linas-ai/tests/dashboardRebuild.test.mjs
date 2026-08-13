/**
 * Tenant Dashboard screen contract checks (no device required).
 * Run: node --test mobile/linas-ai/tests/dashboardRebuild.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = join(root, 'src');

function read(rel) {
  return readFileSync(join(src, ...rel.split('/')), 'utf8');
}

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, out);
    else if (/\.(ts|tsx)$/.test(name)) out.push(p);
  }
  return out;
}

test('Dashboard rebuild uses typed mobile dashboard API', () => {
  const api = read('features/dashboard/dashboardApi.ts');
  const screen = read('features/dashboard/DashboardScreen.tsx');
  const types = read('features/dashboard/dashboardTypes.ts');
  assert.match(api, /\/api\/mobile\/dashboard/);
  assert.match(types, /TenantDashboardSchema/);
  assert.match(types, /activity_summary/);
  assert.match(screen, /DashboardHeader/);
  assert.match(screen, /GrowthPlanCard/);
  assert.match(screen, /TotalActivityGrid/);
  assert.match(screen, /ChannelActivityTable/);
  assert.match(screen, /OwnerCopilotCard/);
  assert.doesNotMatch(screen, /isPlatformOwner|Platform metrics|Owner only|Owner access only/);
  assert.doesNotMatch(screen, /JSON\.stringify/);
  assert.doesNotMatch(types, /\bany\b|@ts-ignore|@ts-nocheck/);
});

test('Dashboard navigation targets real destinations', () => {
  const api = read('features/dashboard/dashboardApi.ts');
  const tree = read('app/AppScreenTree.tsx');
  const nav = read('features/dashboard/dashboardNavigation.ts');
  for (const code of [
    'complete_setup',
    'publish_cm',
    'connect_instagram',
    'review_permissions',
    'renew_subscription',
    'buy_credits',
    'review_faq',
    'manage_users',
  ]) {
    assert.match(api, new RegExp(code));
  }
  assert.match(tree, /onNavigate/);
  assert.match(nav, /name: 'billing'/);
  assert.match(nav, /name: 'integrations'/);
  assert.match(nav, /name: 'cm'/);
  assert.match(nav, /name: 'users'/);
  assert.doesNotMatch(tree, /UsageScreen/);
  assert.doesNotMatch(tree, /name: 'usage'/);
});

test('obsolete Usage screen removed; usage nav redirects to dashboard', () => {
  const drawers = read('features/nav/drawerModules.ts');
  const shell = read('app/AppShell.tsx');
  assert.doesNotMatch(drawers, /id: 'usage'/);
  assert.match(shell, /area === 'usage'/);
  assert.match(shell, /name: 'dashboard'/);
  assert.equal(
    readdirSync(join(src, 'features/billing')).includes('UsageScreen.tsx'),
    false,
  );
});

test('dashboard feature sources stay under 400 lines', () => {
  const files = walk(join(src, 'features/dashboard'));
  for (const file of files) {
    const lines = readFileSync(file, 'utf8').split(/\r?\n/).length;
    assert.ok(lines <= 400, `${file} has ${lines} lines`);
  }
});

test('no OpenAI cost or profit fields in dashboard types/UI', () => {
  const corpus = walk(join(src, 'features/dashboard'))
    .map((f) => readFileSync(f, 'utf8'))
    .join('\n')
    .toLowerCase();
  assert.doesNotMatch(corpus, /cost_usd/);
  assert.doesNotMatch(corpus, /\bopenai\b/);
  assert.doesNotMatch(corpus, /\bprofit\b/);
  assert.doesNotMatch(corpus, /\brevenue\b/);
  assert.doesNotMatch(corpus, /platform\/metrics/);
});

test('dashboard i18n covers en ar fr', () => {
  assert.match(read('i18n/locales/en.ts'), /dashboardEn/);
  assert.match(read('i18n/locales/ar.ts'), /dashboardAr/);
  assert.match(read('i18n/locales/fr.ts'), /dashboardFr/);
  assert.match(read('i18n/locales/dashboardEn.ts'), /dashGrowthPlan/);
});
