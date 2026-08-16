/**
 * AI Setup hub mosaic layout — full-width rows + side-by-side pair rows.
 * Run: node --test mobile/linas-ai/tests/aiSetupHubLayout.test.mjs
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

const SAMPLE_TILES = [
  { id: 'ai_basics', title: 'AI Basics', description: 'd', mobileSupported: true },
  { id: 'knowledge', title: 'Knowledge', description: 'd', mobileSupported: true },
  { id: 'branches', title: 'Locations & hours', description: 'd', mobileSupported: true },
  { id: 'prices', title: 'Service', description: 'd', mobileSupported: true },
  { id: 'comments', title: 'Comments', description: 'd', mobileSupported: true },
  { id: 'requests_appointments', title: 'Requests', description: 'd', mobileSupported: true },
];

describe('AI Setup hub layout', () => {
  it('places AI Basics, Knowledge, and Location as full-width rows at the top', () => {
    const rows = buildAiSetupHubRows(SAMPLE_TILES, true);
    const fullRows = rows.filter((r) => r.type === 'full');
    assert.equal(fullRows.length, 3);
    assert.equal(fullRows[0].item.kind, 'section');
    assert.equal(fullRows[0].item.tile.id, 'ai_basics');
    assert.equal(fullRows[1].item.tile.id, 'knowledge');
    assert.equal(fullRows[2].item.tile.id, 'branches');
  });

  it('orders pair rows: Service+Products, Comments+Requests', () => {
    const rows = buildAiSetupHubRows(SAMPLE_TILES, true);
    const pairs = rows.filter((r) => r.type === 'pair');
    assert.equal(pairs.length, 2);

    assert.equal(pairs[0].left.kind, 'section');
    assert.equal(pairs[0].left.tile.id, 'prices');
    assert.equal(pairs[0].right.kind, 'products');

    assert.equal(pairs[1].left.kind, 'section');
    assert.equal(pairs[1].left.tile.id, 'comments');
    assert.equal(pairs[1].right.kind, 'section');
    assert.equal(pairs[1].right.tile.id, 'requests_appointments');
  });

  it('puts Comments + Requests as the last row', () => {
    const rows = buildAiSetupHubRows(SAMPLE_TILES, true);
    const last = rows[rows.length - 1];
    assert.equal(last.type, 'pair');
    assert.equal(last.left.tile.id, 'comments');
    assert.equal(last.right.tile.id, 'requests_appointments');
  });

  it('CmScreen renders AiSetupHubSections instead of split product grids', () => {
    const screen = read('features/cm/CmScreen.tsx');
    assert.match(screen, /AiSetupHubSections/);
    assert.doesNotMatch(screen, /tilesBeforeProducts/);
    assert.doesNotMatch(screen, /AiSetupProductsCard/);
    const hub = read('features/cm/AiSetupHubSections.tsx');
    assert.match(hub, /buildAiSetupHubRows/);
    assert.match(hub, /AiSetupHubMosaic/);
    assert.match(hub, /variant="full"/);
  });
});
