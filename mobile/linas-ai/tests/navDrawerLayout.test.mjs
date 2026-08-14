/**
 * Drawer layout: Settings beside search, New chat on Recent, AI Setup selected chrome.
 * Run: node --test mobile/linas-ai/tests/navDrawerLayout.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

describe('drawer layout and selected state', () => {
  it('AI Setup uses the same activeRow selected chrome as other tiles', () => {
    const grid = read('features/nav/DrawerNavGrid.tsx');
    assert.match(grid, /const active = activeArea === mod\.id/);
    assert.match(grid, /const tileBg = active \? colors\.activeRow : 'transparent'/);
    assert.doesNotMatch(grid, /active && !isAiSetup/);
    assert.doesNotMatch(grid, /isAiSetup \? styles\.aiSetupTile/);
    assert.doesNotMatch(grid, /featuredIconWrap/);
    assert.match(grid, /modId === 'cm'/);
    assert.match(grid, /LinasSparkleIcon size=\{GRID_ICON_SIZE\}/);
  });

  it('maps AI Setup hub and section screens back to the cm drawer item', () => {
    const nav = read('app/moduleNav.ts');
    assert.match(nav, /case 'cm':/);
    assert.match(nav, /case 'cm_section':/);
    assert.match(nav, /case 'cm':\s*\n\s*case 'cm_section':\s*\n\s*return 'cm'/);
  });

  it('Recent heading matches Linas wordmark size and font', () => {
    const header = read('features/nav/DrawerHeader.tsx');
    const recents = read('features/nav/DrawerRecents.tsx');
    const wordmark = header.match(/wordmark:\s*\{([\s\S]*?)\},/);
    const heading = recents.match(/heading:\s*\{([\s\S]*?)\},/);
    assert.ok(wordmark, 'Linas wordmark style missing');
    assert.ok(heading, 'Recent heading style missing');
    assert.match(wordmark[1], /fontFamily:\s*fonts\.display/);
    assert.match(wordmark[1], /fontSize:\s*18/);
    assert.match(heading[1], /fontFamily:\s*fonts\.display/);
    assert.match(heading[1], /fontSize:\s*18/);
    assert.match(wordmark[1], /letterSpacing:\s*-0\.25/);
    assert.match(heading[1], /letterSpacing:\s*-0\.25/);
  });

  it('header row is search + settings; Recent row is heading + icon-only new chat', () => {
    const header = read('features/nav/DrawerHeader.tsx');
    const recents = read('features/nav/DrawerRecents.tsx');
    const nav = read('features/nav/NavDrawer.tsx');
    assert.match(header, /DRAWER_TOOL_ICONS\.search/);
    assert.match(header, /DRAWER_TOOL_ICONS\.settings/);
    assert.match(header, /onOpenSettings/);
    assert.match(header, /headerActions/);
    assert.match(nav, /onOpenSettings=\{\(\) => openArea\('settings'\)\}/);
    assert.match(recents, /headingRow/);
    assert.match(recents, /NEW_CHAT_ICON/);
    assert.match(recents, /accessibilityLabel=\{tr\('newChat'\)\}/);
    assert.doesNotMatch(recents, /<Text[^>]*>\{tr\('newChat'\)\}<\/Text>/);
    assert.doesNotMatch(recents, /newChatBtn/);
    assert.match(nav, /onNewChat=\{\(\) => \{/);
    assert.doesNotMatch(nav, /DrawerFooter/);
  });

  it('history list fills remaining drawer height under Recent', () => {
    const recents = read('features/nav/DrawerRecents.tsx');
    const nav = read('features/nav/NavDrawer.tsx');
    assert.match(recents, /wrap:\s*\{\s*flex:\s*1/);
    assert.match(recents, /list:\s*\{\s*flex:\s*1/);
    assert.match(recents, /<ScrollView/);
    assert.match(nav, /body:\s*\{\s*flex:\s*1/);
    assert.match(nav, /DrawerNavGrid/);
    assert.match(nav, /DrawerRecents/);
    assert.doesNotMatch(nav, /<DrawerFooter/);
  });
});
