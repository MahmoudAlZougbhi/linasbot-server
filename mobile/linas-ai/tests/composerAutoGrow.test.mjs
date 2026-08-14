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
  COMPOSER_INPUT_LINE_HEIGHT,
  COMPOSER_INPUT_MAX_H,
  COMPOSER_INPUT_MAX_LINES,
  COMPOSER_INPUT_MIN_H,
  COMPOSER_INPUT_PAD_H,
  COMPOSER_MIN_PROBE_WIDTH,
  COMPOSER_PILL_MIN_H,
  composerExceedsMaxLines,
  composerHeightForLines,
  composerHeightFromDraft,
  composerLineBucketChanged,
  lineCountFromDraft,
  newlineCount,
  resolveComposerLineCount,
  targetComposerInputHeight,
  visibleComposerLines,
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
  assert.match(composer, /draft=\{draft\}/);
  const field = read('features/chat/ComposerDraftField.tsx');
  assert.match(field, /value=\{draft\}/);
  assert.doesNotMatch(composer, /inputIdle/);
  assert.doesNotMatch(styles, /absoluteFillObject/);
  assert.doesNotMatch(composer, /placeholderWrap/);
  assert.doesNotMatch(composer, /sendDisabled/);
  assert.doesNotMatch(styles, /opacity:\s*0\.45/);
});

test('auto-grow stays single-line for short text without contentSize', () => {
  assert.equal(targetComposerInputHeight(''), COMPOSER_INPUT_MIN_H);
  assert.equal(targetComposerInputHeight('hi'), COMPOSER_INPUT_MIN_H);
  assert.equal(targetComposerInputHeight('two words', 1), COMPOSER_INPUT_MIN_H);
  assert.equal(resolveComposerLineCount('ab', 1), 1);
  const twoLine = COMPOSER_INPUT_MIN_H + COMPOSER_INPUT_LINE_HEIGHT;
  assert.equal(targetComposerInputHeight('hello there friend', 2), twoLine);
});

test('line-bucket grow: each wrap adds one line until 8, then locks', () => {
  const twoLine = COMPOSER_INPUT_MIN_H + COMPOSER_INPUT_LINE_HEIGHT;
  assert.equal(composerHeightForLines(1), COMPOSER_INPUT_MIN_H);
  assert.equal(composerHeightForLines(2), twoLine);
  let prev = 1;
  for (let wraps = 1; wraps <= 12; wraps += 1) {
    const total = resolveComposerLineCount('hello world example text', wraps);
    const vis = visibleComposerLines(total);
    assert.equal(total, wraps);
    assert.equal(vis, Math.min(COMPOSER_INPUT_MAX_LINES, wraps));
    assert.equal(vis === prev || vis === prev + 1, true);
    assert.equal(targetComposerInputHeight('hello world example text', wraps), composerHeightForLines(vis));
    prev = vis;
  }
  assert.equal(composerHeightForLines(9), COMPOSER_INPUT_MAX_H);
  assert.equal(composerHeightForLines(8), COMPOSER_INPUT_MAX_H);
});

test('same line count does not change height (no jitter / no shrink)', () => {
  const two = composerHeightForLines(2);
  assert.equal(targetComposerInputHeight('hello', 2), two);
  assert.equal(targetComposerInputHeight('hello!', 2), two);
  assert.equal(targetComposerInputHeight('hello!!', 2), two);
  assert.equal(composerLineBucketChanged(2, 2), false);
  assert.equal(composerLineBucketChanged(2, 3), true);
  assert.equal(composerLineBucketChanged(1, 1), false);
});

test('auto-grow caps at max lines and honors explicit newlines', () => {
  assert.equal(COMPOSER_INPUT_MAX_LINES, 8);
  assert.equal(
    COMPOSER_INPUT_MAX_H,
    COMPOSER_INPUT_MIN_H + COMPOSER_INPUT_LINE_HEIGHT * 7,
  );
  const twoLine = COMPOSER_INPUT_MIN_H + COMPOSER_INPUT_LINE_HEIGHT;
  assert.equal(targetComposerInputHeight('a\nb'), twoLine);
  assert.equal(targetComposerInputHeight('long wrap', 20), COMPOSER_INPUT_MAX_H);
});

test('focused bar stacks text above a bottom icon row; empty stays one compact row', () => {
  const composer = read('features/chat/ChatComposer.tsx');
  const styles = read('features/chat/composerStyles.ts');
  const screen = read('features/chat/ChatScreen.tsx');
  const field = read('features/chat/ComposerDraftField.tsx');
  assert.match(composer, /stacked \? styles\.pillStacked : styles\.pillCompact/);
  assert.match(field, /textAlignVertical=\{stacked \|\| fillHeight \? 'top' : 'center'\}/);
  assert.match(field, /scrollEnabled=\{fillHeight \|\| atMaxHeight\}/);
  assert.match(styles, /pillCompact:\s*\{[^}]*flexDirection:\s*'row'/);
  assert.match(styles, /pillStacked:\s*\{[^}]*flexDirection:\s*'column'/);
  assert.match(styles, /actionRow:\s*\{[^}]*justifyContent:\s*'space-between'/);
  assert.match(styles, /inputSlot:\s*\{[^}]*flex:\s*1/);
  assert.match(styles, /minWidth:\s*0/);
  assert.match(screen, /KeyboardAvoidingView/);
  assert.match(screen, /behavior=\{Platform\.OS === 'ios' \? 'padding'/);
});

test('height grows from newlines even when wrap measure stays 1', () => {
  const four = composerHeightForLines(4);
  const eight = composerHeightForLines(8);
  assert.notEqual(four, COMPOSER_INPUT_MIN_H);
  assert.equal(targetComposerInputHeight('a\nb\nc\nd', 1), four);
  assert.equal(targetComposerInputHeight('\n\n\n', 1), composerHeightForLines(4));
  assert.equal(composerHeightFromDraft('\n\n\n\n\n\n\n'), eight);
  assert.equal(lineCountFromDraft('a\nb\nc\nd\ne\nf\ng\nh\ni'), 8);
  assert.equal(newlineCount('a\nb\nc\nd\ne\nf\ng\nh\ni'), 9);

  let height = COMPOSER_INPUT_MIN_H;
  let lines = 1;
  for (const next of ['a', 'a\n', 'a\nb', 'a\nb\n', 'a\nb\nc', 'a\nb\nc\n', 'a\nb\nc\nd']) {
    const total = resolveComposerLineCount(next, 1);
    if (composerLineBucketChanged(lines, total)) {
      lines = total;
      height = composerHeightForLines(visibleComposerLines(total));
    }
  }
  assert.equal(lines, 4);
  assert.equal(height, four);
});

test('expand control only when text exceeds 8 lines; collapse scrolls to end', () => {
  const composer = read('features/chat/ChatComposer.tsx');
  const field = read('features/chat/ComposerDraftField.tsx');
  const autoGrow = read('features/chat/useComposerInputAutoGrow.ts');
  const control = read('features/chat/ComposerExpandControl.tsx');
  assert.equal(composerExceedsMaxLines(8), false);
  assert.equal(composerExceedsMaxLines(9), true);
  assert.equal(visibleComposerLines(12), 8);
  assert.match(composer, /showExpandControl/);
  assert.match(composer, /ComposerDraftField/);
  assert.match(composer, /toggleExpand/);
  assert.match(composer, /scrollComposerToEnd/);
  assert.match(composer, /tr\('composerExpand'\)/);
  assert.match(composer, /tr\('composerCollapse'\)/);
  assert.match(field, /ComposerExpandControl/);
  assert.match(field, /showExpand/);
  assert.match(control, /inward=\{expanded\}/);
  assert.match(autoGrow, /scrollComposerToEnd/);
  assert.match(autoGrow, /showExpandControl/);
  assert.match(composer, /requestAnimationFrame\(scrollComposerToEnd\)/);
});

test('composer grows from draft + hidden wrap measure; contentSize is not in the height path', () => {
  const composer = read('features/chat/ChatComposer.tsx');
  const autoGrow = read('features/chat/useComposerInputAutoGrow.ts');
  const height = read('features/chat/composerInputHeight.ts');
  const styles = read('features/chat/composerStyles.ts');
  const probe = read('features/chat/ComposerHeightProbe.tsx');
  const field = read('features/chat/ComposerDraftField.tsx');
  assert.match(field, /\bmultiline\b/);
  assert.match(field, /ComposerHeightProbe/);
  assert.match(field, /onMeasuredLines/);
  assert.match(field, /minHeight: fillHeight \? undefined : inputHeight/);
  assert.match(autoGrow, /draftRef\.current = next/);
  assert.match(autoGrow, /commitFromDraftAndWraps/);
  assert.match(autoGrow, /handleMeasuredLines/);
  assert.match(autoGrow, /composerLineBucketChanged/);
  assert.doesNotMatch(autoGrow, /handleContentSizeChange/);
  assert.doesNotMatch(autoGrow, /contentHeight/);
  assert.doesNotMatch(field, /onContentSizeChange/);
  assert.doesNotMatch(composer, /onContentSizeChange/);
  assert.doesNotMatch(height, /linesFromContentHeight/);
  assert.doesNotMatch(height, /contentHeight/);
  assert.doesNotMatch(autoGrow, /if \(!currentDraft\.trim\(\)\)/);
  assert.doesNotMatch(autoGrow, /if \(!next\.trim\(\)\)/);
  assert.doesNotMatch(composer, /overflow:\s*'hidden'/);
  assert.doesNotMatch(styles, /overflow:\s*'hidden'/);
  assert.match(styles, /overflow:\s*'visible'/);
  assert.match(probe, /onTextLayout/);
  assert.match(probe, /opacity:\s*0/);
  assert.match(probe, /COMPOSER_MIN_PROBE_WIDTH/);
  assert.equal(COMPOSER_INPUT_PAD_H, 8);
  assert.equal(COMPOSER_MIN_PROBE_WIDTH, 80);
  assert.doesNotMatch(field, /numberOfLines=\{1\}/);
});
