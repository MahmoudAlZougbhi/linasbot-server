/**
 * Per-message script direction (no device required).
 * Run: node --test mobile/linas-ai/tests/*.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function loadTextDirection(isRTL = false) {
  const src = readFileSync(join(root, 'src/lib/textDirection.ts'), 'utf8');
  const js = src
    .replace(
      /import\s+\{[^}]+\}\s+from\s+'react-native';\s*/m,
      'const I18nManager = globalThis.__I18nManager;\n',
    )
    .replace(/export type TextDirectionStyle = \{[\s\S]*?\};/g, '')
    .replace(/\| null \| undefined/g, '')
    .replace(/: TextDirectionStyle/g, '')
    .replace(/: FlexAlignType/g, '')
    .replace(/: ViewStyle/g, '')
    .replace(/: string/g, '')
    .replace(/: number/g, '')
    .replace(/: boolean/g, '')
    .replace(/ as number/g, '')
    .replace(/export /g, '');
  const exports = {};
  globalThis.__I18nManager = { isRTL };
  // eslint-disable-next-line no-new-func
  const fn = new Function(
    'exports',
    `${js}
exports.isRtlText = isRtlText;
exports.textDirectionStyle = textDirectionStyle;
exports.contentStartAlign = contentStartAlign;
exports.aiMessageRowStyle = aiMessageRowStyle;
exports.aiMessageColStyle = aiMessageColStyle;
exports.AI_MESSAGE_EDGE_HUG = AI_MESSAGE_EDGE_HUG;`,
  );
  fn(exports);
  return exports;
}

const {
  isRtlText,
  textDirectionStyle,
  contentStartAlign,
  aiMessageRowStyle,
  aiMessageColStyle,
  AI_MESSAGE_EDGE_HUG,
} = loadTextDirection(false);

test('Arabic message is RTL', () => {
  assert.equal(isRtlText('مرحبا كيفك'), true);
  assert.deepEqual(textDirectionStyle('مرحبا'), {
    textAlign: 'right',
    writingDirection: 'rtl',
  });
});

test('English message is LTR', () => {
  assert.equal(isRtlText('Hello there'), false);
  assert.deepEqual(textDirectionStyle('Hello'), {
    textAlign: 'left',
    writingDirection: 'ltr',
  });
});

test('mixed: first strong Latin stays LTR', () => {
  assert.equal(isRtlText('Hello مرحبا'), false);
});

test('mixed: first strong Arabic is RTL', () => {
  assert.equal(isRtlText('مرحبا Hello'), true);
});

test('leading neutrals/emoji skipped for first strong', () => {
  assert.equal(isRtlText('👋 مرحبا'), true);
  assert.equal(isRtlText('123 Hello'), false);
  assert.equal(isRtlText('... مرحبا'), true);
});

test('empty / punctuation-only defaults LTR', () => {
  assert.equal(isRtlText(''), false);
  assert.equal(isRtlText('   '), false);
  assert.equal(isRtlText('!!!'), false);
  assert.equal(isRtlText(null), false);
});

test('LTR app: EN packs left, AR packs right', () => {
  assert.equal(contentStartAlign('Hello'), 'flex-start');
  assert.equal(contentStartAlign('مرحبا'), 'flex-end');
  assert.deepEqual(aiMessageColStyle('Hello'), { alignItems: 'flex-start' });
  assert.deepEqual(aiMessageColStyle('مرحبا'), { alignItems: 'flex-end' });
});

test('LTR app: AI row hugs matching physical edge', () => {
  assert.deepEqual(aiMessageRowStyle('Hello'), {
    alignSelf: 'stretch',
    maxWidth: '100%',
    marginLeft: -AI_MESSAGE_EDGE_HUG,
    marginRight: 0,
  });
  assert.deepEqual(aiMessageRowStyle('مرحبا'), {
    alignSelf: 'stretch',
    maxWidth: '100%',
    marginLeft: 0,
    marginRight: -AI_MESSAGE_EDGE_HUG,
  });
});

test('RTL app: contentStartAlign still maps to physical EN-left / AR-right', () => {
  const rtlApp = loadTextDirection(true);
  assert.equal(rtlApp.contentStartAlign('Hello'), 'flex-end');
  assert.equal(rtlApp.contentStartAlign('مرحبا'), 'flex-start');
  assert.deepEqual(rtlApp.aiMessageRowStyle('Hello'), {
    alignSelf: 'stretch',
    maxWidth: '100%',
    marginLeft: -rtlApp.AI_MESSAGE_EDGE_HUG,
    marginRight: 0,
  });
  assert.deepEqual(rtlApp.aiMessageRowStyle('مرحبا'), {
    alignSelf: 'stretch',
    maxWidth: '100%',
    marginLeft: 0,
    marginRight: -rtlApp.AI_MESSAGE_EDGE_HUG,
  });
});

test('ChatBubble uses content direction and AI edge align helpers', () => {
  const bubble = readFileSync(join(root, 'src/features/chat/ChatBubble.tsx'), 'utf8');
  assert.match(bubble, /textDirectionStyle/);
  assert.match(bubble, /aiMessageRowStyle/);
  assert.match(bubble, /aiMessageColStyle/);
  assert.match(bubble, /lib\/textDirection/);
  assert.doesNotMatch(bubble, /isRtl\s*\|\|/);
  assert.doesNotMatch(bubble, /useI18n/);
  assert.doesNotMatch(bubble, /detectRtl/);
});

test('composer and live chat wire the same helper', () => {
  const composer = readFileSync(join(root, 'src/features/chat/ChatComposer.tsx'), 'utf8');
  const live = readFileSync(join(root, 'src/features/livechat/LiveChatMessageBubble.tsx'), 'utf8');
  const thinking = readFileSync(join(root, 'src/features/chat/ThinkingRow.tsx'), 'utf8');
  assert.match(composer, /textDirectionStyle\(draft\)/);
  assert.match(composer, /textAlign=\{draftDir\.textAlign\}/);
  assert.match(live, /textDirectionStyle\(body\)/);
  assert.match(thinking, /textDirectionStyle\(label\)/);
  assert.match(thinking, /aiMessageRowStyle\(label\)/);
});
