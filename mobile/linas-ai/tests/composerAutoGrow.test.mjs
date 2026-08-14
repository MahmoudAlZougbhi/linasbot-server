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
  COMPOSER_INPUT_PAD_H,
  COMPOSER_PILL_MIN_H,
  composerHeightForLines,
  composerHeightFromDraft,
  debounceComposerHeight,
  lineCountFromDraft,
  targetComposerInputHeight,
} from '../src/features/chat/composerInputHeight.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = (...p) => join(root, 'src', ...p);

function read(rel) {
  return readFileSync(src(...rel.split('/')), 'utf8');
}

test('idle pill is compact 44pt; send uses sparkle accent', () => {
  const composer = read('features/chat/ChatComposer.tsx');
  const styles = read('features/chat/composerStyles.ts');
  assert.equal(COMPOSER_PILL_MIN_H, 44);
  assert.match(styles, /minHeight:\s*COMPOSER_PILL_MIN_H/);
  assert.match(styles, /height:\s*COMPOSER_PILL_MIN_H/);
  assert.doesNotMatch(styles, /minHeight:\s*52/);
  assert.match(composer, /backgroundColor: colors\.accent \}/);
  assert.doesNotMatch(composer, /backgroundColor: colors\.accentDeep/);
  assert.match(styles, /flexDirection:\s*'row'/);
  assert.match(styles, /flexDirection:\s*'column'/);
  assert.match(styles, /actionRow/);
  assert.match(composer, /placeholder=\{placeholder\}/);
  assert.match(composer, /value=\{draft\}/);
  assert.doesNotMatch(composer, /inputIdle/);
  assert.doesNotMatch(styles, /absoluteFillObject/);
  assert.doesNotMatch(composer, /placeholderWrap/);
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
  assert.equal(first.height, twoLine);
});

test('auto-grow caps at max lines and honors explicit newlines', () => {
  const maxH = COMPOSER_INPUT_MAX_H;
  assert.equal(targetComposerInputHeight(400, 'long wrap'), maxH);
  assert.equal(COMPOSER_INPUT_MAX_LINES, 8);
  assert.equal(
    COMPOSER_INPUT_MAX_H,
    COMPOSER_INPUT_MIN_H + COMPOSER_INPUT_LINE_HEIGHT * 7,
  );
  const twoLine = COMPOSER_INPUT_MIN_H + COMPOSER_INPUT_LINE_HEIGHT;
  assert.equal(targetComposerInputHeight(22, 'a\nb'), twoLine);
});

test('focused bar stacks text above a bottom icon row; empty stays one compact row', () => {
  const composer = read('features/chat/ChatComposer.tsx');
  const styles = read('features/chat/composerStyles.ts');
  const screen = read('features/chat/ChatScreen.tsx');
  assert.match(composer, /stacked \? styles\.pillStacked : styles\.pillCompact/);
  assert.match(composer, /textAlignVertical=\{stacked \? 'top' : 'center'\}/);
  assert.match(composer, /scrollEnabled=\{atMaxHeight\}/);
  assert.match(styles, /pillCompact:\s*\{[^}]*flexDirection:\s*'row'/);
  assert.match(styles, /pillStacked:\s*\{[^}]*flexDirection:\s*'column'/);
  assert.match(styles, /actionRow:\s*\{[^}]*justifyContent:\s*'space-between'/);
  assert.match(styles, /inputSlot:\s*\{[^}]*flex:\s*1/);
  assert.match(styles, /minWidth:\s*0/);
  assert.match(screen, /KeyboardAvoidingView/);
  assert.match(screen, /behavior=\{Platform\.OS === 'ios' \? 'padding'/);
});

test('height grows from newlines even when contentSize stays 36', () => {
  const four = composerHeightForLines(4);
  const eight = composerHeightForLines(8);
  assert.notEqual(four, COMPOSER_INPUT_MIN_H);
  assert.equal(targetComposerInputHeight(COMPOSER_INPUT_MIN_H, 'a\nb\nc\nd'), four);
  assert.equal(targetComposerInputHeight(0, 'a\nb\nc\nd'), four);
  assert.equal(targetComposerInputHeight(36, '\n\n\n'), composerHeightForLines(4));
  assert.equal(composerHeightFromDraft('\n\n\n\n\n\n\n'), eight);
  assert.equal(lineCountFromDraft('a\nb\nc\nd\ne\nf\ng\nh\ni'), 8);

  let height = COMPOSER_INPUT_MIN_H;
  let pending = null;
  let draft = '';
  for (const next of ['a', 'a\n', 'a\nb', 'a\nb\n', 'a\nb\nc', 'a\nb\nc\n', 'a\nb\nc\nd']) {
    draft = next;
    const fromDraft = targetComposerInputHeight(0, draft);
    const grown = debounceComposerHeight(fromDraft, height, pending);
    height = grown.height;
    pending = grown.pending;
    const stuckSize = debounceComposerHeight(
      targetComposerInputHeight(COMPOSER_INPUT_MIN_H, draft),
      height,
      pending,
    );
    height = stuckSize.height;
    pending = stuckSize.pending;
  }
  assert.equal(draft.split('\n').length, 4);
  assert.equal(height, four);
  assert.notEqual(height, COMPOSER_INPUT_MIN_H);
});

test('composer grows from draft onChange and hidden measure, not clipped contentSize', () => {
  const composer = read('features/chat/ChatComposer.tsx');
  const autoGrow = read('features/chat/useComposerInputAutoGrow.ts');
  const height = read('features/chat/composerInputHeight.ts');
  const styles = read('features/chat/composerStyles.ts');
  const probe = read('features/chat/ComposerHeightProbe.tsx');
  assert.match(composer, /\bmultiline\b/);
  assert.match(composer, /scrollEnabled=\{atMaxHeight\}/);
  assert.match(composer, /ComposerHeightProbe/);
  assert.match(composer, /onTextLayout|onMeasuredLines/);
  assert.match(composer, /minHeight: inputHeight/);
  assert.match(autoGrow, /draftRef\.current = next/);
  assert.match(autoGrow, /commitFromDraftAndMeasure/);
  assert.match(autoGrow, /handleMeasuredLines/);
  assert.doesNotMatch(autoGrow, /contentHeight\s*-/);
  assert.doesNotMatch(height, /contentHeight\s*-/);
  assert.doesNotMatch(autoGrow, /if \(!currentDraft\.trim\(\)\)/);
  assert.doesNotMatch(autoGrow, /if \(!next\.trim\(\)\)/);
  assert.doesNotMatch(composer, /overflow:\s*'hidden'/);
  assert.doesNotMatch(styles, /overflow:\s*'hidden'/);
  assert.match(styles, /overflow:\s*'visible'/);
  assert.match(probe, /onTextLayout/);
  assert.match(probe, /opacity:\s*0/);
  assert.equal(COMPOSER_INPUT_PAD_H, 8);
  assert.doesNotMatch(composer, /numberOfLines=\{1\}/);
});
