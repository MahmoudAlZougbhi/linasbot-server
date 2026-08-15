/**
 * Dashboard date-range presets + custom calendar (no device required).
 * Run: node --test mobile/linas-ai/tests/dashboardDateRange.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = join(root, 'src');

function read(rel) {
  return readFileSync(join(src, ...rel.split('/')), 'utf8');
}

function ymd(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function lastCalendarMonth(date) {
  const start = new Date(date.getFullYear(), date.getMonth() - 1, 1);
  const end = new Date(date.getFullYear(), date.getMonth(), 0);
  return { start: ymd(start), end: ymd(end) };
}

test('date sheet presets are All time, Today, Last 7 days, Last month, Last 6 months, Last year, Custom', () => {
  const sheet = read('features/dashboard/sections/DashboardDateRangeSheet.tsx');
  const order = [
    "id: 'all_time'",
    "id: 'today'",
    "id: 'last_7d'",
    "id: 'last_month'",
    "id: 'last_6m'",
    "id: 'last_year'",
  ];
  let from = 0;
  for (const token of order) {
    const at = sheet.indexOf(token, from);
    assert.ok(at >= 0, `missing ${token}`);
    from = at + token.length;
  }
  assert.match(sheet, /dashCustom/);
  assert.match(sheet, /setCalPhase\('start'\)/);
  assert.doesNotMatch(sheet, /id: 'billing'|dashBillingPeriod|id: '30d'|DateStepper|shiftDay/);
});

test('Custom opens the existing month calendar, not a day stepper', () => {
  const sheet = read('features/dashboard/sections/DashboardDateRangeSheet.tsx');
  const picker = read('features/requests/RequestDatePicker.tsx');
  assert.match(sheet, /RequestMonthCalendar/);
  assert.match(sheet, /calPhase === 'end'/);
  assert.match(picker, /export function RequestMonthCalendar/);
  assert.match(picker, /Previous month/);
  assert.match(picker, /Next month/);
  assert.match(picker, /month: 'long', year: 'numeric'/);
  assert.match(picker, /Date calendar/);
});

test('last month is the previous calendar month, not rolling 30 days', () => {
  const format = read('features/dashboard/dashboardFormat.ts');
  assert.match(format, /lastCalendarMonthRange/);
  assert.match(format, /getMonth\(\) - 1/);
  assert.match(format, /new Date\(date\.getFullYear\(\), date\.getMonth\(\), 0\)/);
  assert.deepEqual(lastCalendarMonth(new Date(2026, 7, 15)), {
    start: '2026-07-01',
    end: '2026-07-31',
  });
  assert.deepEqual(lastCalendarMonth(new Date(2026, 0, 10)), {
    start: '2025-12-01',
    end: '2025-12-31',
  });
});

test('presets resolve to custom start/end for activity queries', () => {
  const api = read('features/dashboard/dashboardApi.ts');
  const format = read('features/dashboard/dashboardFormat.ts');
  assert.match(api, /dashboardQueryRange/);
  assert.match(api, /params\.set\('period', 'custom'\)/);
  assert.match(api, /params\.set\('start', range\.start\)/);
  assert.match(api, /params\.set\('end', range\.end\)/);
  assert.match(format, /id === 'today'/);
  assert.match(format, /getMonth\(\) - 6/);
  assert.match(format, /getMonth\(\) - 12/);
});

test('Today / Last 7 days / Last month query named API periods in the device timezone', () => {
  const api = read('features/dashboard/dashboardApi.ts');
  const format = read('features/dashboard/dashboardFormat.ts');
  const types = read('features/dashboard/dashboardTypes.ts');
  const screen = read('features/dashboard/DashboardScreen.tsx');
  assert.match(format, /namedDashboardApiPeriod/);
  assert.match(format, /today: 'today'/);
  assert.match(format, /last_7d: '7d'/);
  assert.match(format, /last_month: 'last_month'/);
  assert.match(format, /getFullYear\(\)/);
  assert.match(format, /getDate\(\)/);
  assert.doesNotMatch(format, /toISOString\(\)\.slice\(0, 10\)/);
  assert.match(api, /namedDashboardApiPeriod\(period\)/);
  assert.match(api, /params\.set\('period', named\)/);
  assert.match(types, /'last_month'/);
  assert.match(screen, /dashboardQueryRange\(period\)/);
  assert.doesNotMatch(screen, /setUTCDate/);
  const localMidnight = new Date(2026, 7, 15, 0, 30);
  assert.equal(ymd(localMidnight), '2026-08-15');
});

test('Last 7 days is today plus the previous 6 local calendar days', () => {
  const format = read('features/dashboard/dashboardFormat.ts');
  assert.match(format, /lastSevenDaysRange/);
  assert.match(format, /getDate\(\) - 6/);
  const date = new Date(2026, 7, 15);
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate() - 6);
  assert.equal(ymd(start), '2026-08-09');
  assert.equal(ymd(date), '2026-08-15');
});

test('default period is All time encoded as custom 1970-01-01 through today', () => {
  const hook = read('features/dashboard/useTenantDashboard.ts');
  const format = read('features/dashboard/dashboardFormat.ts');
  const api = read('features/dashboard/dashboardApi.ts');
  assert.match(format, /DEFAULT_DASHBOARD_PERIOD/);
  assert.match(format, /id: 'all_time'/);
  assert.match(format, /id === 'all_time'/);
  assert.match(format, /start: '1970-01-01'/);
  assert.match(hook, /initialPeriod \?\? DEFAULT_DASHBOARD_PERIOD/);
  assert.match(hook, /resetToDefaultPeriod/);
  assert.match(api, /dashboardQueryRange/);
  assert.match(api, /params\.set\('period', 'custom'\)/);
  assert.doesNotMatch(hook, /monthStartIso|todayIso/);
});

test('refresh keeps the last snapshot and does not treat missing activity as zero', () => {
  const hook = read('features/dashboard/useTenantDashboard.ts');
  const grid = read('features/dashboard/sections/TotalActivityGrid.tsx');
  assert.match(hook, /if \(soft\) setRefreshing\(true\)/);
  assert.match(hook, /else if \(!snapshotRef\.current\) setState\(\{ kind: 'loading' \}\)/);
  assert.match(hook, /refresh: \(\) => load\(\{ soft: true \}\)/);
  assert.match(hook, /periodRef\.current/);
  assert.match(hook, /if \(snapshotRef\.current\)/);
  assert.match(hook, /requestId !== requestIdRef\.current/);
  assert.match(grid, /unavailable \|\| value == null \? '—' : formatCount\(value\)/);
  assert.doesNotMatch(grid, /unavailable \|\| !activity \? 0/);
});

test('date filter i18n covers EN AR FR and drops billing / last 30 days', () => {
  const en = read('i18n/locales/dashboardEn.ts');
  const ar = read('i18n/locales/dashboardAr.ts');
  const fr = read('i18n/locales/dashboardFr.ts');
  for (const [src, allTime, today, last7, lastMonth, last6, lastYear, custom] of [
    [en, 'All time', 'Today', 'Last 7 days', 'Last month', 'Last 6 months', 'Last year', 'Custom'],
    [ar, 'كل الوقت', 'اليوم', 'آخر 7 أيام', 'الشهر الماضي', 'آخر 6 أشهر', 'السنة الماضية', 'مخصص'],
    [fr, 'Tout le temps', 'Aujourd’hui', '7 derniers jours', 'Mois dernier', '6 derniers mois', 'Année dernière', 'Personnalisé'],
  ]) {
    assert.match(src, new RegExp(allTime));
    assert.match(src, new RegExp(today));
    assert.match(src, new RegExp(last7));
    assert.match(src, new RegExp(lastMonth));
    assert.match(src, new RegExp(last6));
    assert.match(src, new RegExp(lastYear));
    assert.match(src, new RegExp(custom));
    assert.doesNotMatch(src, /Billing period|فترة الفوترة|Période de facturation/);
    assert.doesNotMatch(src, /Last 30 days|آخر 30 يوماً|30 derniers jours/);
  }
});

test('Owner Copilot uses the Linas sparkle logo, not Ionicons sparkles', () => {
  const copilot = read('features/dashboard/sections/OwnerCopilotCard.tsx');
  assert.match(copilot, /LinasSparkleIcon size=\{20\} color=\{colors\.accentDeep\}/);
  assert.doesNotMatch(copilot, /name="sparkles"/);
  assert.doesNotMatch(copilot, /DASH_FOREST/);
});
