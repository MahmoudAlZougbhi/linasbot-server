/**
 * AI Setup hub: Live AI toggle + 7-section progress (no Greeting/Style inflation).
 * Run: node --test mobile/linas-ai/tests/aiSetupLiveAndProgress.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { buildAiSetupHubRows } from '../src/features/cm/aiSetupHubLayout.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

const HUB_TILES = [
  { id: 'ai_basics', title: 'AI Basics', description: 'd', mobileSupported: true },
  { id: 'knowledge', title: 'Knowledge', description: 'd', mobileSupported: true },
  { id: 'branches', title: 'Locations & hours', description: 'd', mobileSupported: true },
  { id: 'prices', title: 'Services', description: 'd', mobileSupported: true },
  { id: 'comments', title: 'Comments', description: 'd', mobileSupported: true },
  { id: 'requests_appointments', title: 'Requests', description: 'd', mobileSupported: true },
];

describe('AI Setup Live toggle + hub section count', () => {
  it('hub mosaic has exactly 7 tiles including Products', () => {
    const rows = buildAiSetupHubRows(HUB_TILES, true);
    const ids = [];
    for (const row of rows) {
      if (row.type === 'full') {
        ids.push(row.item.kind === 'products' ? 'products' : row.item.tile.id);
      } else {
        ids.push(row.left.kind === 'products' ? 'products' : row.left.tile.id);
        ids.push(row.right.kind === 'products' ? 'products' : row.right.tile.id);
      }
    }
    assert.deepEqual(ids, [
      'ai_basics',
      'knowledge',
      'branches',
      'prices',
      'products',
      'comments',
      'requests_appointments',
    ]);
    assert.equal(ids.length, 7);
  });

  it('progress allowlist is 7 hub sections and ignores style/greetings/faq/actions', () => {
    const sections = read('features/cm/cmSections.ts');
    const hub = read('features/cm/cmHubProgress.ts');
    assert.match(sections, /CM_HUB_PROGRESS_TOTAL = CM_HUB_PROGRESS_SECTION_IDS\.length \+ 1/);
    assert.match(
      sections,
      /CM_HUB_PROGRESS_SECTION_IDS[\s\S]*ai_basics[\s\S]*knowledge[\s\S]*branches[\s\S]*prices[\s\S]*comments[\s\S]*requests_appointments/s,
    );
    assert.match(hub, /CM_HUB_PROGRESS_TOTAL/);
    assert.match(hub, /productsComplete/);
    assert.match(hub, /CM_HUB_PRODUCTS_PROGRESS_ID/);
    assert.doesNotMatch(hub, /faq|actions|ai_limits|style|dynamic_messages/);
  });

  it('Live badge is a real publish/unpublish control', () => {
    const card = read('features/cm/AiSetupProgressCard.tsx');
    const screen = read('features/cm/CmScreen.tsx');
    const api = read('features/cm/cmApi.ts');
    assert.match(card, /onToggleLive/);
    assert.match(card, /accessibilityRole="switch"/);
    assert.match(card, /aiSetupOff/);
    assert.match(screen, /publishCmLive/);
    assert.match(screen, /unpublishCmLive/);
    assert.match(screen, /onToggleLive=\{onToggleLive\}/);
    assert.match(api, /\/api\/cm\/publish/);
    assert.match(api, /\/api\/cm\/unpublish/);
  });
});
