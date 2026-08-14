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

test('chat header: overlay hamburger only in light-gray square', () => {
  const header = read('features/chat/ChatHeader.tsx');
  const icons = read('features/chat/ChatHeaderIcons.tsx');
  const chat = read('features/chat/ChatScreen.tsx');
  const footer = read('features/nav/DrawerFooter.tsx');
  assert.match(header, /HeaderIconBox/);
  assert.match(header, /colors\.featuredIconBg/);
  assert.match(header, /colors\.featuredIconBorder/);
  assert.match(header, /MenuIcon/);
  assert.match(header, /ChatTopFade/);
  assert.match(header, /LIST_BELOW_OVERLAY_GAP = spacing\.md \+ spacing\.sm/);
  assert.match(header, /CHAT_LIST_TOP_CLEARANCE = HEADER_HIT \+ HEADER_TOP_GAP \+ LIST_BELOW_OVERLAY_GAP/);
  assert.match(header, /position:\s*'absolute'/);
  assert.match(header, /pointerEvents="box-none"/);
  assert.match(header, /right:\s*0/);
  assert.match(header, /direction:\s*'ltr'/);
  assert.doesNotMatch(header, /LinasStarMark/);
  assert.doesNotMatch(header, /label="Linas AI"/);
  assert.doesNotMatch(header, /NewChatIcon/);
  assert.doesNotMatch(header, /onNewChat/);
  assert.doesNotMatch(header, /borderBottomWidth/);
  assert.doesNotMatch(header, /from ['"]expo-blur['"]/);
  assert.match(icons, /export function HeaderIconBox/);
  assert.match(icons, /HEADER_ICON_BOX/);
  assert.match(chat, /<ChatHeader[\s\S]*onOpenMenu=/);
  assert.doesNotMatch(chat, /<ChatHeader[\s\S]{0,180}onNewChat=/);
  assert.doesNotMatch(chat, /styles\.flex, \{ paddingTop: insets\.top \}/);
  const fade = read('features/chat/ChatTopFade.tsx');
  assert.match(fade, /pointerEvents="none"/);
  assert.match(fade, /hexRgba/);
  assert.doesNotMatch(fade, /from ['"]expo-blur['"]/);
  const list = read('features/chat/ChatMessageList.tsx');
  assert.match(list, /CHAT_LIST_TOP_CLEARANCE/);
  assert.match(list, /contentInsetAdjustmentBehavior="never"/);
  assert.match(list, /insets\.top \+ CHAT_LIST_TOP_CLEARANCE/);
  const listStyles = read('features/chat/chatScreenStyles.ts');
  assert.match(listStyles, /paddingTop:\s*16/);
  assert.match(footer, /tr\('newChat'\)/);
  assert.match(footer, /<NewChatIcon /);
});

test('composer: pill with plus, placeholder, mic, in-pill send, disclaimer', () => {
  const composer = read('features/chat/ChatComposer.tsx');
  const pill = read('features/chat/composerStyles.ts');
  const height = read('features/chat/composerInputHeight.ts');
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
  assert.match(pill, /direction:\s*'ltr'/);
  assert.match(glyphs, /COMPOSER_SEND_SIZE = 36/);
  assert.match(glyphs, /COMPOSER_PLUS_DISK = 32/);
  assert.match(glyphs, /PLUS_STROKE = 1\.75/);
  assert.match(glyphs, /ion\('arrow-up'\)/);
  assert.match(glyphs, /feather\('mic'\)/);
  assert.match(composer, /backgroundColor=\{colors\.featuredIconBg\}/);
  assert.match(composer, /borderColor=\{colors\.featuredIconBorder\}/);
  assert.match(composer, /placeholder=\{placeholder\}/);
  assert.match(composer, /value=\{draft\}/);
  assert.match(pill, /justifyContent:\s*'center'/);
  assert.match(pill, /actionRow/);
  assert.match(pill, /minHeight:\s*COMPOSER_PILL_MIN_H/);
  assert.match(height, /COMPOSER_PILL_MIN_H = 44/);
  assert.doesNotMatch(pill, /minHeight:\s*52/);
  assert.match(en, /composerPlaceholder:\s*'Chat with Linas'/);
  assert.match(en, /composerPlaceholderChat:\s*'Chat with Linas'/);
  assert.match(en, /composerPlaceholderWork:\s*'Work with Linas'/);
  assert.match(en, /composerDisclaimer:\s*'Linas can make mistakes\. Check important info\.'/);
  assert.match(ar, /composerPlaceholderChat:\s*'دردش مع Linas'/);
  assert.match(ar, /composerPlaceholderWork:\s*'اعمل مع Linas'/);
  assert.match(fr, /composerPlaceholderChat:\s*'Discutez avec Linas'/);
  assert.match(fr, /composerPlaceholderWork:\s*'Travaillez avec Linas'/);
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

test('chat thread starts high; sparkle matches Linas name; send is sparkle teal', () => {
  const screen = read('features/chat/ChatScreen.tsx');
  const scroll = read('features/chat/useChatListScroll.ts');
  const toggle = read('features/chat/ChatModeToggle.tsx');
  const bubble = read('features/chat/ChatBubble.tsx');
  const mark = read('components/LinasStarMark.tsx');
  const composer = read('features/chat/ChatComposer.tsx');
  const drawer = read('features/nav/DrawerHeader.tsx');
  assert.match(screen, /armOpenAtLatest\(\{ pinToLatest: hasUserMessage \}\)/);
  assert.match(scroll, /pinToLatest === false/);
  assert.match(scroll, /scrollToOffset\(\{ offset: 0/);
  assert.match(toggle, /position:\s*'absolute'/);
  assert.match(bubble, /labelColor=\{colors\.text\}/);
  assert.match(drawer, /styles\.wordmark, \{ color: colors\.text \}/);
  assert.match(mark, /fontSize:\s*size/);
  assert.match(mark, /lineHeight:\s*size/);
  assert.match(composer, /backgroundColor: colors\.accent \}/);
  assert.match(composer, /isRtl/);
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
