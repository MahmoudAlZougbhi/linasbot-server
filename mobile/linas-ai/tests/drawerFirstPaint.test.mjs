/**
 * Drawer first paint: recents/badge cache, chat chrome hidden while open.
 * Run: node --test mobile/linas-ai/tests/drawerFirstPaint.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, it } from 'node:test';

import {
  clearDrawerSessionCache,
  getCachedDrawerBadges,
  getCachedDrawerRecents,
  rememberDrawerRecents,
  replaceDrawerRecents,
  setCachedDrawerBadges,
} from '../src/features/nav/drawerSessionCache.ts';
import { drawerTileBadge } from '../src/features/nav/drawerTileBadge.ts';
import { visibleRecentItems } from '../src/features/nav/visibleRecentItems.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

afterEach(() => {
  clearDrawerSessionCache();
});

describe('session cache keeps last known recents and badge', () => {
  it('does not replace filled recents with an empty bootstrap', () => {
    rememberDrawerRecents(
      [
        { id: 'a', title: 'Pricing help' },
        { id: 'b', title: 'Hours question' },
      ],
      [],
    );
    rememberDrawerRecents([], []);
    const cached = getCachedDrawerRecents();
    assert.deepEqual(
      cached.history.map((h) => h.title),
      ['Pricing help', 'Hours question'],
    );
  });

  it('lets a real API empty list replace cache', () => {
    rememberDrawerRecents([{ id: 'a', title: 'Pricing help' }], []);
    replaceDrawerRecents([], []);
    assert.deepEqual(getCachedDrawerRecents().history, []);
  });

  it('keeps last known AI Setup percent', () => {
    setCachedDrawerBadges({
      aiSetupPercent: 83,
      liveChatUnread: 0,
      requestsPending: 0,
    });
    assert.equal(getCachedDrawerBadges().aiSetupPercent, 83);
    assert.deepEqual(drawerTileBadge('cm', getCachedDrawerBadges()), {
      label: '83%',
      tone: 'teal',
    });
  });

  it('visibleRecentItems keeps non-archived titles', () => {
    const rows = visibleRecentItems(
      [
        { id: 'a', title: 'Pricing help' },
        { id: 'b', title: 'Archived chat' },
      ],
      ['b'],
    );
    assert.deepEqual(
      rows.map((r) => r.title),
      ['Pricing help'],
    );
  });
});

describe('drawer paints cache immediately and hides chat chrome', () => {
  it('prefetches badges and recents while authenticated, not only on open', () => {
    const badges = read('features/nav/useDrawerBadges.ts');
    const history = read('features/nav/useModuleDrawerHistory.ts');
    const nav = read('features/nav/NavDrawer.tsx');
    assert.match(badges, /getCachedDrawerBadges/);
    assert.match(badges, /useState<DrawerBadges>\(getCachedDrawerBadges\)/);
    assert.match(badges, /\[enabled\]/);
    assert.match(badges, /refreshDrawerBadges/);
    assert.match(history, /getCachedDrawerRecents/);
    assert.match(history, /void refresh\(\)/);
    assert.match(nav, /rememberDrawerRecents\(props\.history, props\.archivedIds\)/);
    assert.match(nav, /visibleRecentItems\(props\.history, props\.archivedIds\)/);
  });

  it('hides hamburger and Chat/Work while the drawer is open', () => {
    const chat = read('features/chat/ChatScreen.tsx');
    const header = read('features/chat/ChatHeader.tsx');
    const toggle = read('features/chat/ChatModeToggle.tsx');
    const drawer = read('components/SideDrawer.tsx');
    assert.match(chat, /\{\!drawerOpen \? \(/);
    assert.match(chat, /<ChatHeader/);
    assert.match(chat, /showModeToggle && !drawerOpen/);
    assert.match(header, /zIndex:\s*20/);
    assert.match(toggle, /zIndex:\s*15/);
    assert.match(drawer, /export const DRAWER_Z = 40/);
    assert.match(drawer, /zIndex:\s*DRAWER_Z/);
    assert.match(drawer, /elevation:\s*DRAWER_Z/);
    assert.match(drawer, /paddingBottom:\s*0/);
    assert.match(drawer, /backgroundColor:\s*colors\.drawerSurface/);
  });

  it('keeps drawer search/settings in the menu header', () => {
    const header = read('features/nav/DrawerHeader.tsx');
    const recents = read('features/nav/DrawerRecents.tsx');
    assert.match(header, /DRAWER_TOOL_ICONS\.search/);
    assert.match(header, /DRAWER_TOOL_ICONS\.settings/);
    assert.match(header, /wordmark/);
    assert.match(recents, /removeClippedSubviews=\{false\}/);
    assert.match(recents, /paddingBottom:\s*Math\.max\(insets\.bottom,\s*8\)/);
  });
});
