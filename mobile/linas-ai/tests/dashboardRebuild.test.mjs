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
  assert.match(screen, /BuyCreditsSheet/);
  assert.match(screen, /credits\.setOpen\(true\)/);
  assert.match(screen, /headerRight/);
  assert.match(screen, /resetToDefaultPeriod/);
  assert.match(read('app/AppScreenTree.tsx'), /active=\{name === 'dashboard'\}/);
  assert.doesNotMatch(screen, /stackedHeader/);
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

test('dashboard date card uses new presets and Linas copilot mark', () => {
  const sheet = read('features/dashboard/sections/DashboardDateRangeSheet.tsx');
  const copilot = read('features/dashboard/sections/OwnerCopilotCard.tsx');
  assert.match(sheet, /dashAllTime/);
  assert.match(sheet, /dashToday/);
  assert.match(sheet, /dashLastMonth/);
  assert.match(sheet, /RequestMonthCalendar/);
  assert.doesNotMatch(sheet, /dashBillingPeriod/);
  assert.match(copilot, /LinasSparkleIcon/);
  assert.doesNotMatch(copilot, /name="sparkles"/);
});

test('Growth plan header divider and Total activity card stroke match siblings', () => {
  const growth = read('features/dashboard/sections/GrowthPlanCard.tsx');
  const grid = read('features/dashboard/sections/TotalActivityGrid.tsx');
  const channels = read('features/dashboard/sections/ChannelActivityTable.tsx');
  assert.match(growth, /headerRule/);
  assert.match(growth, /DASH_TRACK/);
  assert.match(grid, /borderWidth: 1/);
  assert.match(grid, /borderColor: colors\.border/);
  assert.match(channels, /borderWidth: 1/);
});

test('Total activity Smart Q&A uses the drawer FAQ glyph, not sparkles', () => {
  const grid = read('features/dashboard/sections/TotalActivityGrid.tsx');
  const modules = read('features/nav/moduleIcons.ts');
  const channels = read('features/dashboard/sections/ChannelActivityTable.tsx');
  assert.match(modules, /faq: feather\('help-circle'\)/);
  assert.match(grid, /MODULE_ICONS\.faq/);
  assert.match(grid, /DASH_ICON_BG/);
  assert.doesNotMatch(grid, /sparkles-outline/);
  assert.doesNotMatch(channels, /sparkles-outline/);
});
