/**
 * Note/Description: first 10 lines inline, then See all (Copy + X).
 * Run: node --test mobile/linas-ai/tests/longTextSeeAll.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  countTextLines,
  needsSeeAll,
  NOTE_TEXT_COLOR,
  SEE_ALL_MAX_LINES,
} from '../src/features/cm/longTextClamp.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

describe('See all long text', () => {
  it('shows See all only after more than 10 lines', () => {
    assert.equal(SEE_ALL_MAX_LINES, 10);
    assert.equal(countTextLines('one\ntwo'), 2);
    assert.equal(needsSeeAll('short'), false);
    assert.equal(needsSeeAll(Array.from({ length: 10 }, (_, i) => `L${i}`).join('\n')), false);
    assert.equal(needsSeeAll(Array.from({ length: 11 }, (_, i) => `L${i}`).join('\n')), true);
    assert.equal(NOTE_TEXT_COLOR, '#000000');
  });

  it('wires clamp + fullscreen Copy/X on Note and Description fields', () => {
    const field = read('features/cm/editors/Field.tsx');
    const clamp = read('features/cm/ClampedLongField.tsx');
    const modal = read('features/cm/SeeAllTextModal.tsx');
    const en = read('i18n/locales/aiSetupEn.ts');
    assert.match(field, /if \(multiline\)/);
    assert.match(field, /ClampedLongField/);
    assert.match(clamp, /SEE_ALL_MAX_LINES|seeAllMaxHeight/);
    assert.match(clamp, /tr\('aiSetupSeeAll'\)/);
    assert.match(clamp, /ScrollView/);
    assert.match(clamp, /pointerEvents="none"/);
    assert.match(clamp, /keyboardShouldPersistTaps="never"/);
    assert.match(clamp, /NOTE_TEXT_COLOR/);
    assert.match(modal, /feather\('x'\)/);
    assert.match(modal, /Clipboard\.setStringAsync/);
    assert.match(modal, /tr\('aiSetupCopy'\)/);
    assert.match(modal, /onChangeText=\{persist\}/);
    assert.match(modal, /NOTE_TEXT_COLOR/);
    assert.match(en, /aiSetupSeeAll: 'See all'/);
    assert.match(en, /aiSetupCopy: 'Copy'/);
    assert.match(read('features/cm/knowledge/KnowledgeEditView.tsx'), /ClampedLongField/);
    assert.match(read('features/services/ServiceEditView.tsx'), /ClampedLongField/);
    assert.match(read('features/cm/comments/CommentEditView.tsx'), /ClampedLongField/);
    assert.match(read('features/cm/requestRules/RequestRuleEditView.tsx'), /ClampedLongField/);
    assert.match(read('features/cm/resources/ResourceMetaModal.tsx'), /ClampedLongField/);
  });
});
