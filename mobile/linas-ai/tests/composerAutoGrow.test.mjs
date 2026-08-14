/**
 * Composer idle height, send color token, and auto-grow stability.
 * Run: node --test mobile/linas-ai/tests/composerAutoGrow.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import {
  COMPOSER_GROW_SLACK,
  COMPOSER_INPUT_LINE_HEIGHT,
  COMPOSER_INPUT_MAX_H,
  COMPOSER_INPUT_MAX_LINES,
  COMPOSER_INPUT_MIN_H,
  COMPOSER_PILL_MIN_H,
  debounceComposerHeight,
  targetComposerInputHeight,
} from '../src/features/chat/composerInputHeight.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = (...p) => join(root, 'src', ...p);

function read(rel) {
  return readFileSync(src(...rel.split('/')), 'utf8');
}

test('idle pill is compact 44pt; send uses sparkle accent', () => {
  const composer = read('features/chat/ChatComposer.tsx');
  const bubble = read('features/chat/ChatBubble.tsx');
  const mark = read('components/LinasStarMark.tsx');
  const styles = read('features/chat/composerStyles.ts');
  assert.equal(COMPOSER_PILL_MIN_H, 44);
  assert.match(styles, /minHeight:\s*COMPOSER_PILL_MIN_H/);
  assert.match(styles, /height:\s*COMPOSER_PILL_MIN_H/);
  assert.doesNotMatch(styles, /minHeight:\s*52/);
  assert.match(composer, /backgroundColor: colors\.accent \}/);
  assert.doesNotMatch(composer, /backgroundColor: colors\.accentDeep/);
  assert.match(bubble, /labelColor=\{colors\.text\}/);
  assert.match(mark, /fontSize:\s*size/);
  assert.match(styles, /inputIdle/);
  assert.match(styles, /placeholderWrap/);
  assert.match(styles, /placeholderWrap:\s*\{[^}]*justifyContent:\s*'center'/);
  assert.doesNotMatch(composer, /sendDisabled/);
  assert.doesNotMatch(styles, /opacity:\s*0\.45/);
});

test('auto-grow stays single-line for short text and iOS contentSize bounce', () => {
  assert.equal(targetComposerInputHeight(22, ''), COMPOSER_INPUT_MIN_H);
  assert.equal(targetComposerInputHeight(50, ''), COMPOSER_INPUT_MIN_H);
  assert.equal(targetComposerInputHeight(22, 'hi'), COMPOSER_INPUT_MIN_H);
  assert.equal(targetComposerInputHeight(36, 'two words'), COMPOSER_INPUT_MIN_H);
  assert.equal(
    targetComposerInputHeight(COMPOSER_INPUT_MIN_H + COMPOSER_GROW_SLACK, 'two words'),
    COMPOSER_INPUT_MIN_H,
  );
  const wrapped = COMPOSER_INPUT_MIN_H + COMPOSER_GROW_SLACK + 1;
  const twoLine = COMPOSER_INPUT_MIN_H + COMPOSER_INPUT_LINE_HEIGHT;
  assert.equal(targetComposerInputHeight(wrapped, 'hello there friend'), twoLine);
  assert.equal(targetComposerInputHeight(44, 'hello there friend'), twoLine);

  let pending = null;
  let height = COMPOSER_INPUT_MIN_H;
  for (const measured of [36, 40, 36, 41, 22, 36]) {
    const target = targetComposerInputHeight(measured, 'ab');
    const next = debounceComposerHeight(target, height, pending);
    pending = next.pending;
    height = next.height;
  }
  assert.equal(height, COMPOSER_INPUT_MIN_H);

  const growTarget = targetComposerInputHeight(44, 'hello there friend');
  const first = debounceComposerHeight(growTarget, COMPOSER_INPUT_MIN_H, null);
  assert.equal(first.height, COMPOSER_INPUT_MIN_H);
  const second = debounceComposerHeight(growTarget, first.height, first.pending);
  assert.equal(second.height, twoLine);
});

test('auto-grow caps at max lines and honors explicit newlines', () => {
  const maxH = COMPOSER_INPUT_MAX_H;
  assert.equal(targetComposerInputHeight(400, 'long wrap'), maxH);
  assert.equal(COMPOSER_INPUT_MAX_LINES, 8);
  const twoLine = COMPOSER_INPUT_MIN_H + COMPOSER_INPUT_LINE_HEIGHT;
  assert.equal(targetComposerInputHeight(22, 'a\nb'), twoLine);
});
