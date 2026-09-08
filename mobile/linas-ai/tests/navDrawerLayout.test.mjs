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

  it('Chats heading matches the Live Chat screen title size', () => {
    const recents = read('features/nav/DrawerRecents.tsx');
    const chrome = read('features/shared/ScreenChrome.tsx');
    const type = read('theme/typography.ts');
    const heading = recents.match(/heading:\s*\{([\s\S]*?)\},/);
    assert.ok(heading, 'Chats heading style missing');
    assert.match(heading[1], /\.\.\.typography\.title/);
    assert.match(type, /title:[\s\S]*?fontSize:\s*26/);
    assert.match(chrome, /: typography\.title/);
    assert.doesNotMatch(heading[1], /typography\.drawerItem/);
  });

  it('Pin section sits above Recent with pin glyph on pinned rows', () => {
    const recents = read('features/nav/DrawerRecents.tsx');
    const rows = read('features/nav/HistoryRows.tsx');
    assert.match(recents, /tr\('drawerPin'\)/);
    assert.match(recents, /tr\('drawerRecents'\)/);
    assert.match(recents, /pinned\.length/);
    assert.match(recents, /items=\{pinned\}/);
    assert.match(recents, /items=\{recent\}/);
    assert.match(rows, /showPin/);
    assert.match(rows, /DRAWER_TOOL_ICONS\.pin/);
    assert.doesNotMatch(rows, /drawerRows/);
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

  it('module tiles and chat titles share drawerItem size and medium fill', () => {
    const type = read('theme/typography.ts');
    const grid = read('features/nav/DrawerNavGrid.tsx');
    const rows = read('features/nav/HistoryRows.tsx');
    const modules = read('features/nav/drawerModules.ts');
    assert.match(type, /drawerItem:[\s\S]*?fontFamily:\s*bodyMedium/);
    assert.match(type, /drawerItem:[\s\S]*?fontSize:\s*16/);
    assert.match(type, /drawerItem:[\s\S]*?lineHeight:\s*22/);
    assert.match(grid, /label:\s*\{\s*\.\.\.typography\.drawerItem,/);
    assert.match(rows, /rowTitleDrawer:\s*\{\s*\.\.\.typography\.drawerItem,/);
    assert.match(modules, /titleKey:\s*'navTeam'/);
  });

  it('drawer body is one ScrollView; Recents is not a nested flex-1 scroller', () => {
    const recents = read('features/nav/DrawerRecents.tsx');
    const nav = read('features/nav/NavDrawer.tsx');
    const drawer = read('components/SideDrawer.tsx');
    assert.match(nav, /<ScrollView/);
    assert.match(nav, /<DrawerHeader/);
    assert.match(nav, /DrawerNavGrid/);
    assert.match(nav, /DrawerRecents/);
    assert.match(nav, /paddingBottom:\s*Math\.max\(insets\.bottom,\s*8\)/);
    assert.match(nav, /body:\s*\{\s*flex:\s*1/);
    assert.doesNotMatch(nav, /<DrawerFooter/);
    assert.doesNotMatch(nav, /APP_VERSION_LABEL/);
    assert.doesNotMatch(recents, /ScrollView/);
    assert.doesNotMatch(recents, /flex:\s*1/);
    assert.match(recents, /<HistoryRows/);
    assert.match(drawer, /paddingBottom:\s*0/);
    assert.match(drawer, /styles\.body/);
    assert.doesNotMatch(drawer, /paddingBottom:\s*Math\.max\(insets\.bottom/);
  });
});
