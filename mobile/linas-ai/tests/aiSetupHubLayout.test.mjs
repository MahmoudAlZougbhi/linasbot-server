/**
 * AI Setup hub mosaic layout — full-width rows + big/two-small mosaic.
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
  { id: 'knowledge', title: 'Knowledge', description: 'd', mobileSupported: true },
  { id: 'ai_basics', title: 'AI Basics', description: 'd', mobileSupported: true },
  { id: 'dynamic_messages', title: 'Greetings', description: 'd', mobileSupported: true },
  { id: 'services', title: 'Services', description: 'd', mobileSupported: true },
  { id: 'branches', title: 'Branches', description: 'd', mobileSupported: true },
  { id: 'prices', title: 'Service', description: 'd', mobileSupported: true },
  { id: 'comments', title: 'Comments', description: 'd', mobileSupported: true },
  { id: 'requests_appointments', title: 'Requests', description: 'd', mobileSupported: true },
];

describe('AI Setup hub layout', () => {
  it('places Knowledge and Service (prices) as full-width rows at the top', () => {
    const rows = buildAiSetupHubRows(SAMPLE_TILES, true);
    assert.equal(rows[0].type, 'full');
    assert.equal(rows[0].item.kind, 'section');
    assert.equal(rows[0].item.tile.id, 'knowledge');
    assert.equal(rows[1].type, 'full');
    assert.equal(rows[1].item.tile.id, 'prices');
  });

  it('chunks remaining sections into big + two-small mosaic rows with Products at the end', () => {
    const rows = buildAiSetupHubRows(SAMPLE_TILES, true);
    const mosaic = rows.filter((r) => r.type === 'mosaic');
    assert.equal(mosaic.length, 3);

    assert.equal(mosaic[0].big.kind, 'section');
    assert.equal(mosaic[0].big.tile.id, 'ai_basics');
    assert.deepEqual(
      mosaic[0].smalls.map((s) => (s.kind === 'products' ? 'products' : s.tile.id)),
      ['dynamic_messages', 'services'],
    );

    assert.equal(mosaic[1].big.kind, 'section');
    assert.equal(mosaic[1].big.tile.id, 'branches');
    assert.deepEqual(
      mosaic[1].smalls.map((s) => s.tile.id),
      ['comments', 'requests_appointments'],
    );

    assert.equal(mosaic[2].big.kind, 'products');
    assert.equal(mosaic[2].smalls.length, 0);
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
