/**
 * AI Setup — legacy sections hidden from owner hub (care, handoff, restricted).
 * Run: node --test mobile/linas-ai/tests/aiSetupHiddenSections.test.mjs
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

describe('AI Setup hub hides legacy sections', () => {
  it('marks care, handoff, and restricted as hub-hidden', () => {
    const src = read('features/cm/cmSections.ts');
    for (const id of ['care', 'handoff', 'restricted']) {
      assert.match(src, new RegExp(`id: '${id}'[\\s\\S]*?showInCmHub: false`));
    }
    assert.match(src, /CM_HUB_PROGRESS_EXCLUDED.*care.*handoff.*restricted/s);
    assert.doesNotMatch(src, /CM_HUB_CARDS[\s\S]*id: 'care'/);
    assert.doesNotMatch(src, /CM_HUB_CARDS[\s\S]*id: 'handoff'/);
    assert.doesNotMatch(src, /CM_HUB_CARDS[\s\S]*id: 'restricted'/);
  });

  it('keeps section editors for deep links and copilot proposals', () => {
    const screen = read('features/cm/CmSectionScreen.tsx');
    assert.match(screen, /case 'care':/);
    assert.match(screen, /case 'handoff':/);
    assert.match(screen, /case 'restricted':/);
  });

  it('excludes hidden sections from hub progress helper', () => {
    const src = read('features/cm/cmHubProgress.ts');
    assert.match(src, /CM_HUB_PROGRESS_SECTION_IDS/);
    assert.match(src, /summarizeHubProgress/);
    assert.match(src, /CM_HUB_PROGRESS_TOTAL/);
    assert.match(src, /productsComplete/);
  });

  it('CmScreen and drawer badge use hub-filtered progress', () => {
    const screen = read('features/cm/CmScreen.tsx');
    const badges = read('features/nav/useDrawerBadges.ts');
    assert.match(screen, /summarizeHubProgress/);
    assert.match(screen, /displaySummary\.percent/);
    assert.match(badges, /summarizeHubProgress/);
  });
});
