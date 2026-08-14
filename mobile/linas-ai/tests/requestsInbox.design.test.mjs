import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = (...p) => join(root, 'src', ...p);
const read = (...p) => readFileSync(src(...p), 'utf8');

test('requests list matches inbox screenshot chrome', () => {
  const home = read('features/requests/RequestsHome.tsx');
  const search = read('features/requests/RequestSearchBar.tsx');
  const summary = read('features/requests/RequestSummaryCards.tsx');
  const screen = read('features/requests/RequestsScreen.tsx');
  assert.match(home, /RequestSummaryCards/);
  assert.match(home, /RequestSearchBar/);
  assert.match(home, /RequestFilterSheet/);
  assert.match(home, /All platforms/);
  assert.match(search, /Search name, phone, or request/);
  assert.match(search, /feather\('sliders'\)/);
  assert.match(search, /filterActive/);
  assert.match(summary, /In progress/);
  assert.match(summary, /Done/);
  assert.match(screen, /reqSubtitle/);
  assert.doesNotMatch(home, /ChipRow|TYPE_CHIPS|DATE_CHIPS/);
});

test('request cards expose status assign chat print', () => {
  const row = read('features/requests/RequestCardRow.tsx');
  const actions = read('features/requests/RequestCardActions.tsx');
  assert.match(row, /Request #/);
  assert.match(row, /PlatformChannelIcon/);
  assert.match(row, /RequestCardActions/);
  assert.match(actions, /Chat/);
  assert.match(actions, /Print/);
  assert.match(actions, /Assign/);
  assert.match(actions, /In progress/);
});

test('filter sheet has platforms date assignee reset and show count', () => {
  const sheet = read('features/requests/RequestFilterSheet.tsx');
  const format = read('features/requests/requestsFormat.ts');
  assert.match(sheet, /Filter requests/);
  assert.match(sheet, /Platforms/);
  assert.match(sheet, /Date range/);
  assert.match(sheet, /Assigned user/);
  assert.match(sheet, /Reset/);
  assert.match(sheet, /Show \$\{matched\} requests/);
  assert.match(sheet, /tiktok/);
  assert.match(format, /whatsapp_cloud/);
  assert.match(format, /instagram_dm/);
  assert.match(format, /FILTER_PLATFORMS/);
});
