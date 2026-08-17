/**
 * Drawer recents visibility, AI Setup badge, and first-paint status.
 * Run: node --test mobile/linas-ai/tests/drawerRecentsBadgeSetup.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { resolveAiSetupSectionPaint } from '../src/features/cm/aiSetupSectionPaint.ts';
import { drawerTileBadge } from '../src/features/nav/drawerTileBadge.ts';
import { visibleRecentItems } from '../src/features/nav/visibleRecentItems.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

describe('drawer recents render when history exists', () => {
  it('keeps non-archived chats for the Recent list', () => {
    const rows = visibleRecentItems(
      [
        { id: 'a', title: 'Pricing help' },
        { id: 'b', title: 'Archived chat' },
        { id: 'c', title: 'Hours question' },
      ],
      ['b'],
    );
    assert.deepEqual(
      rows.map((r) => r.id),
      ['a', 'c'],
    );
    assert.equal(rows[0].title, 'Pricing help');
  });

  it('passes those items into HistoryRows inside the Recents block', () => {
    const recents = read('features/nav/DrawerRecents.tsx');
    const nav = read('features/nav/NavDrawer.tsx');
    const rows = read('features/nav/HistoryRows.tsx');
    assert.match(nav, /visibleRecentItems\(props\.history, props\.archivedIds\)/);
    assert.match(recents, /items=\{pinned\}/);
    assert.match(recents, /items=\{recent\}/);
    assert.match(recents, /tr\('drawerPin'\)/);
    assert.match(recents, /<HistoryRows/);
    assert.doesNotMatch(recents, /ScrollView/);
    assert.match(rows, /if \(!items\.length\)/);
    assert.match(rows, /items\.map\(renderRow\)/);
  });
});

describe('AI Setup drawer badge when count > 0', () => {
  it('shows the percent badge when setup is incomplete', () => {
    const badge = drawerTileBadge('cm', {
      aiSetupPercent: 42,
      liveChatUnread: 0,
      requestsPending: 0,
    });
    assert.deepEqual(badge, { label: '42%', tone: 'teal' });
  });

  it('hides the badge only when setup is complete', () => {
    assert.equal(
      drawerTileBadge('cm', {
        aiSetupPercent: 100,
        liveChatUnread: 0,
        requestsPending: 0,
      }),
      null,
    );
    assert.equal(
      drawerTileBadge('cm', {
        aiSetupPercent: null,
        liveChatUnread: 0,
        requestsPending: 0,
      }),
      null,
    );
  });

  it('paints the badge above the tile, not clipped inside Pressable', () => {
    const grid = read('features/nav/DrawerNavGrid.tsx');
    assert.match(grid, /drawerTileBadge\(mod\.id, badges\)/);
    assert.match(grid, /styles\.tileWrap/);
    assert.match(grid, /pointerEvents="none"/);
    assert.match(grid, /zIndex:\s*4/);
    assert.match(grid, /top:\s*-4/);
    assert.match(grid, /overflow:\s*'visible'/);
  });
});

describe('AI Setup status is not missing before load resolves', () => {
  it('treats unknown fill as pending, not missing', () => {
    assert.equal(resolveAiSetupSectionPaint(undefined), 'pending');
    assert.equal(resolveAiSetupSectionPaint('incomplete'), 'missing');
    assert.equal(resolveAiSetupSectionPaint('complete'), 'complete');
  });

  it('does not paint section status until the first fetch hydrates', () => {
    const screen = read('features/cm/CmScreen.tsx');
    const tile = read('features/cm/AiSetupSectionTile.tsx');
    assert.match(screen, /const \[hydrated, setHydrated\] = useState\(false\)/);
    assert.match(screen, /setHydrated\(true\)/);
    assert.match(screen, /hasLoadedOnce && hydrated/);
    assert.match(tile, /resolveAiSetupSectionPaint/);
    assert.match(tile, /paint === 'missing'/);
    assert.doesNotMatch(tile, /fill !== 'complete'/);
  });
});
