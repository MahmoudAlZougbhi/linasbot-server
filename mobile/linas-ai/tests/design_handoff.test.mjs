/**
 * Mobile design-handoff unit checks (no device required).
 * Run: node --test mobile/linas-ai/tests/*.test.mjs
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

test('drawer module order matches binding product order', () => {
  const text = read('features/nav/drawerModules.ts');
  const ids = [...text.matchAll(/id: '([a-z]+)'/g)].map((m) => m[1]);
  assert.deepEqual(ids, [
    'dashboard',
    'cm',
    'faq',
    'livechat',
    'integrations',
    'users',
    'subscription',
    'usage',
    'settings',
  ]);
});

test('drawer and CM module tiles expose design handoff icons', () => {
  const nav = read('features/nav/NavDrawer.tsx');
  const modules = read('features/nav/moduleIcons.ts');
  const cm = read('features/cm/CmScreen.tsx');
  const cmIcons = read('features/cm/cmSectionIcons.ts');
  assert.match(nav, /MODULE_ICONS/);
  assert.match(nav, /AppIcon/);
  assert.match(modules, /dashboard: feather\('grid'\)/);
  assert.match(modules, /cm: feather\('book-open'\)/);
  assert.match(modules, /livechat: feather\('message-square'\)/);
  assert.match(modules, /integrations: mci\('power-plug-outline'\)/);
  assert.match(modules, /usage: feather\('upload-cloud'\)/);
  assert.match(modules, /subscription: feather\('credit-card'\)/);
  assert.match(modules, /settings: feather\('settings'\)/);
  assert.match(cm, /CM_SECTION_ICONS/);
  assert.match(cmIcons, /ai_basics: feather\('book-open'\)/);
  assert.match(cmIcons, /languages: feather\('globe'\)/);
});

test('NavDrawer is physical-left only', () => {
  const nav = read('features/nav/NavDrawer.tsx');
  assert.match(nav, /side="left"/);
  assert.doesNotMatch(nav, /side=\{isRtl \? 'right'/);
  assert.doesNotMatch(nav, /side="right"/);
});

test('ChatScreen has no right Control Center drawer and no mascot avatar state', () => {
  const chat = read('features/chat/ChatScreen.tsx');
  assert.doesNotMatch(chat, /ControlCenterDrawer/);
  assert.doesNotMatch(chat, /LinasAvatar/);
  assert.doesNotMatch(chat, /avatarState/);
  assert.match(chat, /NavDrawer/);
  assert.match(chat, /showPlus=\{isAuthenticated\}/);
  assert.match(chat, /showMic=\{isAuthenticated\}/);
});

test('App launches chat-first for guest and owner', () => {
  const app = readFileSync(join(root, 'App.tsx'), 'utf8');
  assert.match(app, /setScreen\(\{ name: 'chat' \}\)/);
  assert.doesNotMatch(app, /name: 'creative'/);
  assert.doesNotMatch(app, /CreativeStudio/);
});

test('proposal card exposes complete V2 actions beyond Review/Discard', () => {
  const card = read('features/chat/v2/ProposalCard.tsx');
  for (const needle of [
    'Approve and apply to Draft',
    'Review in Content Management',
    'Discard',
    'CURRENT',
    'PROPOSED',
    'Not applied yet',
  ]) {
    assert.match(card, new RegExp(needle));
  }
});

test('guest pending draft handoff does not import transcript', () => {
  const draft = read('features/chat/pendingGuestDraft.ts');
  assert.match(draft, /never imports guest transcript/i);
  assert.match(draft, /savePendingGuestDraft/);
  assert.match(draft, /clearPendingGuestDraft/);
});

test('voice STT wires transcript into composer draft (no auto-send)', () => {
  const voice = read('features/chat/useVoiceDraft.ts');
  const chat = read('features/chat/ChatScreen.tsx');
  const composer = read('features/chat/ChatComposer.tsx');
  const formData = read('api/formDataFile.ts');
  assert.match(voice, /apiUpload\('\/api\/mobile\/transcribe'/);
  assert.match(voice, /appendLocalFile\(form, 'audio'/);
  assert.match(voice, /onTextRef\.current\(text\)/);
  assert.doesNotMatch(voice, /expo-av/);
  assert.doesNotMatch(voice, /form\.append\(\s*'audio'\s*,\s*\{/);
  assert.match(formData, /expo-file-system/);
  assert.match(formData, /Unsupported FormDataPart/);
  assert.match(chat, /useVoiceDraft\(\(text\) =>/);
  assert.match(chat, /setDraft/);
  assert.match(chat, /showMic=\{isAuthenticated\}/);
  assert.match(composer, /showVoiceControl/);
  assert.match(composer, /recording \|\| transcribing \|\| !canSend/);
  assert.match(composer, /Listening…/);
  assert.match(composer, /Transcribing…/);
  assert.match(composer, /MicGlyph/);
  assert.match(composer, /StopGlyph/);
  assert.doesNotMatch(composer, /🎙/);
});

test('Live Chat thread remains read-only', () => {
  const thread = read('features/livechat/LiveChatThread.tsx');
  assert.match(thread, /read-only/i);
  assert.match(thread, /StatusChip label="Read-only"/);
  assert.doesNotMatch(thread, /LiveChatComposer/);
  assert.doesNotMatch(thread, /onSendMessage/);
  assert.doesNotMatch(thread, /function\s+takeover|pauseAi|humanTakeover/i);
});

test('drawer search filters chats; New chat is bottom-left not header-right', () => {
  const nav = read('features/nav/NavDrawer.tsx');
  const header = read('features/chat/ChatHeader.tsx');
  const chat = read('features/chat/ChatScreen.tsx');
  const headerCall = chat.match(/<ChatHeader[\s\S]*?\/>/)?.[0] || '';
  assert.match(nav, /bottomDock/);
  assert.match(nav, /newChatBtn/);
  assert.match(nav, /searchConversationTitles/);
  assert.match(nav, /noChatsMatch/);
  assert.match(nav, /emptyLabel/);
  assert.doesNotMatch(header, /onNewChat/);
  assert.doesNotMatch(header, /NewChatIcon/);
  assert.match(headerCall, /<ChatHeader/);
  assert.doesNotMatch(headerCall, /onNewChat/);
  assert.match(chat, /<NavDrawer[\s\S]*onNewChat=/);
});

test('Settings hosts Notifications and Logout; drawer does not', () => {
  const settings = read('features/settings/SettingsScreen.tsx');
  const nav = read('features/nav/NavDrawer.tsx');
  const chat = read('features/chat/ChatScreen.tsx');
  const app = readFileSync(join(root, 'App.tsx'), 'utf8');
  assert.match(settings, /onOpenNotifications/);
  assert.match(settings, /notificationsTitle/);
  assert.match(settings, /tr\('logout'\)/);
  assert.doesNotMatch(nav, /onOpenNotifications/);
  assert.doesNotMatch(nav, /onLogout/);
  assert.doesNotMatch(nav, /Notifications/);
  assert.doesNotMatch(nav, /Log out/);
  assert.doesNotMatch(chat, /onLogout/);
  assert.match(app, /onOpenNotifications=\{\(\) => setScreen\(\{ name: 'notifications', backTo: 'settings' \}\)\}/);
});

test('Settings does not duplicate AI Basics CM store', () => {
  const settings = read('features/settings/SettingsScreen.tsx');
  assert.match(settings, /Content Management for AI Basics/);
  assert.doesNotMatch(settings, /MFA/);
  assert.doesNotMatch(settings, /Passkey/);
});

test('Integrations Test Connection is read-only refresh + App A filter', () => {
  const integ = read('features/integrations/IntegrationsScreen.tsx');
  assert.match(integ, /Test connection \(read-only refresh\)/);
  assert.match(integ, /does not reconnect/);
  assert.match(integ, /platform === 'instagram' \|\| row\.platform === 'facebook'/);
});

test('theme tokens include light and dark parity keys', () => {
  const tokens = read('theme/tokens.ts');
  assert.match(tokens, /export const lightColors/);
  assert.match(tokens, /export const darkColors/);
  assert.match(tokens, /accent: '#0D9488'/);
});

test('no bottom tab navigator wiring', () => {
  const app = readFileSync(join(root, 'App.tsx'), 'utf8');
  assert.doesNotMatch(app, /createBottomTabNavigator|BottomTab|Tab\.Navigator/);
});
