/**
 * Leave-prompt dirty flag must compare payload content, not object identity.
 * Run: node --import ./tests/resolveTsSibling.mjs --experimental-strip-types --test tests/cmDraftDirty.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { isDraftDirty, stableSerialize } from '../src/features/cm/cmDraftDirty.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

describe('cmDraftDirty', () => {
  it('treats key-order and clone differences as clean', () => {
    const loaded = { items: [{ id: 'b1', notes: null, maps_url: '' }], revision: 1 };
    const clone = { revision: 1, items: [{ maps_url: '', notes: null, id: 'b1' }] };
    const baseline = stableSerialize(loaded);
    assert.equal(isDraftDirty(baseline, clone), false);
    assert.equal(isDraftDirty(baseline, { ...loaded, items: [{ ...loaded.items[0], notes: 'x' }] }), true);
  });

  it('useCmDraft and Locations back only prompt when snapshot differs', () => {
    const draft = readFileSync(join(root, 'src/features/cm/useCmDraft.ts'), 'utf8');
    const screen = readFileSync(join(root, 'src/features/cm/LocationHoursSectionScreen.tsx'), 'utf8');
    assert.match(draft, /baselineRef/);
    assert.match(draft, /isDraftDirty\(baselineRef\.current/);
    assert.match(draft, /setDirty\(overlay\)/);
    assert.doesNotMatch(draft, /setDirty\(true\)/);
    assert.match(screen, /if \(!draft\.dirty\)/);
    assert.match(screen, /aiSetupLocUnsavedTitle/);
  });
});
