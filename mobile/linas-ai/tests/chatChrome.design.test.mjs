/**
 * In-app chat chrome vs screenshot handoff (header, bubbles, composer, model menu).
 * Run: node --test mobile/linas-ai/tests/chatChrome.design.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = (...p) => join(root, 'src', ...p);

function read(rel) {
  return readFileSync(src(...rel.split('/')), 'utf8');
}

test('chat header: hamburger + new-chat in light-gray squares, sparkle title', () => {
  const header = read('features/chat/ChatHeader.tsx');
  const icons = read('features/chat/ChatHeaderIcons.tsx');
  assert.match(header, /HeaderIconBox/);
  assert.match(header, /colors\.featuredIconBg/);
  assert.match(header, /colors\.featuredIconBorder/);
  assert.match(header, /label="Linas AI"/);
  assert.match(header, /LinasStarMark/);
  assert.match(header, /MenuIcon/);
  assert.match(header, /NewChatIcon/);
  assert.match(header, /direction:\s*'ltr'/);
  assert.match(header, /borderBottomWidth:\s*StyleSheet\.hairlineWidth/);
  assert.match(icons, /export function HeaderIconBox/);
  assert.match(icons, /HEADER_ICON_BOX/);
  assert.match(icons, /NEW_CHAT_ICON/);
});

test('composer: pill with plus, placeholder, mic, in-pill send, disclaimer', () => {
  const composer = read('features/chat/ChatComposer.tsx');
  const glyphs = read('features/chat/ComposerGlyphs.tsx');
  const en = read('i18n/locales/en.ts');
  const ar = read('i18n/locales/ar.ts');
  const fr = read('i18n/locales/fr.ts');
  assert.match(composer, /styles\.pill/);
  assert.match(composer, /PlusCircleGlyph/);
  assert.match(composer, /SendArrowGlyph/);
  assert.match(composer, /sendInside/);
  assert.doesNotMatch(composer, /sendOutside/);
  assert.match(composer, /tr\('composerDisclaimer'\)/);
  assert.match(composer, /direction:\s*'ltr'/);
  assert.match(glyphs, /COMPOSER_SEND_SIZE = 32/);
  assert.match(en, /composerPlaceholder:\s*'Message Linas AI'/);
  assert.match(en, /composerDisclaimer:\s*'Linas can make mistakes\. Check important info\.'/);
  assert.match(ar, /composerPlaceholder:\s*'راسل Linas AI'/);
  assert.match(fr, /composerPlaceholder:\s*'Messagez Linas AI'/);
});

test('model chip maps chat/work to existing 5.6 LIN Low/High ids', () => {
  const chip = read('features/chat/ComposerModelChip.tsx');
  const sheet = read('features/chat/LinEffortSheet.tsx');
  const mode = read('features/chat/ownerChatMode.ts');
  const en = read('i18n/locales/en.ts');
  assert.match(mode, /OWNER_LIN_DISPLAY = '5\.6 LIN'/);
  assert.match(mode, /OwnerChatMode = 'chat' \| 'work'/);
  assert.match(mode, /effortLabelForMode/);
  assert.match(chip, /modelChipLabel/);
  assert.match(sheet, /id: 'chat'/);
  assert.match(sheet, /id: 'work'/);
  assert.match(sheet, /linEffortLow/);
  assert.match(sheet, /linEffortHigh/);
  assert.match(sheet, /linEffortFast/);
  assert.match(sheet, /linEffortHighSub/);
  assert.match(sheet, /feather\('zap'\)/);
  assert.match(sheet, /feather\('check'\)/);
  assert.match(en, /linEffortLow:\s*'Low'/);
  assert.match(en, /linEffortHigh:\s*'High'/);
  assert.match(en, /linEffortFast:\s*'Fast'/);
  assert.match(en, /linEffortHighSub:\s*'More powerful'/);
});

test('bubbles: You / Linas labels, mint user bubble, teal AI bullets', () => {
  const bubble = read('features/chat/ChatBubble.tsx');
  const body = read('features/chat/AiMessageBody.tsx');
  const tokens = read('theme/tokens.ts');
  const list = read('features/chat/ChatMessageList.tsx');
  const en = read('i18n/locales/en.ts');
  assert.match(bubble, /userLabel/);
  assert.match(bubble, /linasLabel/);
  assert.match(bubble, /colors\.bubbleUser/);
  assert.match(bubble, /LinasStarMark/);
  assert.match(list, /tr\('chatYouLabel'\)/);
  assert.match(list, /tr\('chatLinasLabel'\)/);
  assert.match(list, /direction:\s*'ltr'|styles\.ltr/);
  assert.match(en, /chatYouLabel:\s*'You'/);
  assert.match(en, /chatLinasLabel:\s*'Linas'/);
  assert.match(tokens, /bubbleUser:\s*'#E8F2F0'/);
  assert.match(body, /colors\.accent/);
  assert.match(body, /kind: 'section'/);
  assert.match(body, /kind: 'bullet'/);
});
