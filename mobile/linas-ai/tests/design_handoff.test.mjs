/**
 * Mobile design-handoff unit checks (no device required).
 * Run: node --test mobile/linas-ai/tests/*.test.mjs
 */
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
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
  const overlays = read('features/chat/ChatScreenOverlays.tsx');
  assert.doesNotMatch(chat, /ControlCenterDrawer/);
  assert.doesNotMatch(chat, /LinasAvatar/);
  assert.doesNotMatch(chat, /avatarState/);
  assert.match(overlays, /NavDrawer/);
  assert.match(chat, /showPlus=\{isAuthenticated\}/);
  assert.match(chat, /showMic=\{isAuthenticated\}/);
});

test('Chat|Work toggle shows on new owner chat despite greeting seed', () => {
  const chat = read('features/chat/ChatScreen.tsx');
  const mode = read('features/chat/ChatModeToggle.tsx');
  const session = read('features/chat/useChatSession.ts');
  assert.match(mode, /Segmented Chat \| Work/);
  assert.match(chat, /ChatModeToggle/);
  assert.match(chat, /hasUserMessage/);
  assert.match(chat, /showModeToggle/);
  assert.match(chat, /isAuthenticated && !hasUserMessage/);
  assert.doesNotMatch(chat, /messages\.length === 0 && !turn\.liveText/);
  assert.match(session, /setMessages\(\[\]\)/);
});

test('App launches chat-first for guest and owner', () => {
  const app = readFileSync(join(root, 'App.tsx'), 'utf8');
  assert.match(app, /setScreen\(\{ name: 'chat' \}\)/);
  assert.doesNotMatch(app, /name: 'creative'/);
  assert.doesNotMatch(app, /CreativeStudio/);
});

test('cold open is branded star splash then chat (no character mash / progress boot)', () => {
  const boot = read('features/boot/BootSplash.tsx');
  const index = readFileSync(join(root, 'index.ts'), 'utf8');
  const appJson = readFileSync(join(root, 'app.json'), 'utf8');
  const chat = read('features/chat/ChatScreen.tsx');
  const login = read('features/auth/LoginScreen.tsx');
  assert.match(boot, /splash-icon\.png/);
  assert.match(boot, /isReduceMotionEnabled|reduceMotionChanged/);
  assert.match(boot, /SplashScreen\.hideAsync/);
  assert.doesNotMatch(boot, /LinasAvatar/);
  assert.doesNotMatch(boot, /Opening Linas AI/);
  assert.doesNotMatch(boot, /progressTrack|styles\.track/);
  assert.match(index, /preventAutoHideAsync/);
  assert.match(appJson, /"backgroundColor":\s*"#0B3D34"/);
  assert.match(appJson, /"bundleIdentifier":\s*"com\.linasai\.app"/);
  assert.match(appJson, /"package":\s*"com\.linasai\.app"/);
  assert.match(appJson, /expo-audio/);
  assert.match(appJson, /"buildNumber":\s*"18"/);
  assert.match(appJson, /"versionCode":\s*18/);
  assert.doesNotMatch(
    chat,
    /if \(loading\) \{\s*return \(\s*<GradientBackground>\s*<View style=\{styles\.center\}>/,
  );
  assert.match(chat, /loading \? \(/);
  assert.match(login, /BrandMark/);
  assert.doesNotMatch(login, /linasAssets|authHero|LinasAvatar|avatarAssets/);
});

test('no character/mascot PNG assets remain in the mobile bundle', () => {
  const assetsDir = join(root, 'assets');
  const names = readdirSync(assetsDir);
  for (const banned of [
    'linas-auth-hero.png',
    'linas-avatar-chat.png',
    'linas-avatar-circle.png',
    'linas-avatar-small.png',
    'linas-brand-sheet.png',
    'linas-empty-state.png',
    'linas-portrait-source.png',
    'linas-ui-board.jpg',
  ]) {
    assert.equal(existsSync(join(assetsDir, banned)), false, banned);
  }
  assert.equal(
    names.some((n) => /^linas-(state|expr)-/.test(n)),
    false,
    'no linas-state-* / linas-expr-* character frames',
  );
  assert.equal(existsSync(join(root, 'src/features/linas')), false);
  assert.ok(names.includes('splash-icon.png'));
  assert.ok(names.includes('icon.png'));
});


test('owner stream shows Thinking then live bubble in the same footer slot', () => {
  const turn = read('features/chat/v2/useStreamingTurn.ts');
  const footer = read('features/chat/ChatStreamFooter.tsx');
  const list = read('features/chat/ChatMessageList.tsx');
  const chat = read('features/chat/ChatScreen.tsx');
  const thinking = read('features/chat/ThinkingRow.tsx');
  assert.match(turn, /setThinking\(true\)/);
  assert.match(turn, /onDelta:[\s\S]*setThinking\(false\)/);
  assert.match(turn, /onError:[\s\S]*resetUi\(\)/);
  assert.match(footer, /thinking && !liveText/);
  assert.match(footer, /ThinkingRow/);
  assert.match(footer, /tr\('chatThinking'\)/);
  assert.match(footer, /id: 'live-stream'/);
  assert.match(list, /thinking=\{thinking\}/);
  assert.match(chat, /thinking=\{turn\.thinking\}/);
  assert.match(thinking, /isReduceMotionEnabled|reduceMotionChanged/);
  assert.match(thinking, /LinasStarMark/);
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
  const controls = read('features/chat/VoiceComposerControls.tsx');
  const glyphs = read('features/chat/ComposerGlyphs.tsx');
  const formData = read('api/formDataFile.ts');
  const send = read('features/chat/sendChatMessage.ts');
  assert.match(voice, /apiUpload\('\/api\/mobile\/transcribe'/);
  assert.match(voice, /appendLocalFile\(form, 'audio'/);
  assert.match(voice, /onTextRef\.current\(text\)/);
  assert.match(voice, /'paused'/);
  assert.match(voice, /recorder\.pause\(\)/);
  assert.match(voice, /resumeVoice/);
  assert.match(voice, /confirmVoice/);
  assert.match(voice, /discardVoice/);
  assert.match(voice, /durationMillis/);
  assert.doesNotMatch(voice, /expo-av/);
  assert.doesNotMatch(voice, /form\.append\(\s*'audio'\s*,\s*\{/);
  assert.match(formData, /expo-file-system/);
  assert.match(formData, /Unsupported FormDataPart/);
  assert.match(chat, /useVoiceDraft\(\(text\) =>/);
  assert.match(chat, /setDraft/);
  assert.match(chat, /showMic=\{isAuthenticated\}/);
  assert.match(chat, /onResumeVoice/);
  assert.match(chat, /onConfirmVoice/);
  assert.match(chat, /onDiscardVoice/);
  assert.match(composer, /showVoiceControl/);
  assert.match(composer, /voiceBusy \|\| !canSend/);
  assert.match(composer, /Listening…/);
  assert.match(composer, /Paused ·/);
  assert.match(composer, /Transcribing…/);
  assert.match(composer, /formatVoiceElapsed/);
  assert.match(composer, /StopGlyph/);
  assert.match(controls, /Continue recording/);
  assert.match(controls, /Use recording/);
  assert.match(controls, /Discard recording/);
  assert.match(glyphs, /export function MicGlyph/);
  assert.match(glyphs, /export function StopGlyph/);
  assert.match(glyphs, /export function formatVoiceElapsed/);
  assert.match(send, /voiceState === 'paused'/);
  assert.doesNotMatch(composer, /🎙/);
});

test('LIN effort chip opens Low/High picker synced with Chat|Work', () => {
  const composer = read('features/chat/ChatComposer.tsx');
  const sheet = read('features/chat/LinEffortSheet.tsx');
  const chat = read('features/chat/ChatScreen.tsx');
  const mode = read('features/chat/ownerChatMode.ts');
  assert.match(composer, /onOwnerModeChange/);
  assert.match(composer, /LinEffortSheet/);
  assert.match(composer, /accessibilityRole="button"/);
  assert.match(sheet, /linEffortLow/);
  assert.match(sheet, /linEffortHigh/);
  assert.match(sheet, /linEffortCostsMore/);
  assert.match(sheet, /CloudGlyph/);
  assert.match(sheet, /id: 'chat'/);
  assert.match(sheet, /id: 'work'/);
  assert.match(chat, /onOwnerModeChange=\{setOwnerMode\}/);
  assert.match(mode, /effortLabelForMode/);
});

test('Live Chat thread remains read-only', () => {
  const thread = read('features/livechat/LiveChatThread.tsx');
  assert.match(thread, /read-only/i);
  assert.match(thread, /StatusChip label="Read-only"/);
  assert.doesNotMatch(thread, /LiveChatComposer/);
  assert.doesNotMatch(thread, /onSendMessage/);
  assert.doesNotMatch(thread, /function\s+takeover|pauseAi|humanTakeover/i);
});

test('drawer search chrome is header circle; New chat is compact bottom dock', () => {
  const nav = read('features/nav/NavDrawer.tsx');
  const chat = read('features/chat/ChatScreen.tsx');
  const overlays = read('features/chat/ChatScreenOverlays.tsx');
  const drawer = read('components/SideDrawer.tsx');
  assert.match(nav, /bottomDock/);
  assert.match(nav, /newChatBtn/);
  assert.match(nav, /searchCircle/);
  assert.match(nav, /headerDivider/);
  assert.match(nav, /searchConversationTitles/);
  assert.match(nav, /noChatsMatch/);
  assert.match(nav, /emptyLabel/);
  assert.match(nav, /VERSION_LABEL/);
  assert.match(nav, /APP_VERSION_LABEL/);
  const configSrc = read('config.ts');
  assert.match(configSrc, /Constants\.expoConfig\?\.version/);
  assert.match(configSrc, /APP_VERSION_LABEL/);
  assert.match(configSrc, /APP_BUILD_LABEL/);
  // Version is pinned bottom-left of the drawer footer (under New Chat row).
  assert.match(nav, /alignSelf:\s*'flex-start'/);
  assert.match(nav, /textAlign:\s*'left'/);
  assert.match(nav, /justifyContent:\s*'flex-end'/);
  assert.ok(nav.lastIndexOf('{VERSION_LABEL}') > nav.indexOf('newChatBtn'));
  // Search mode hides Dashboard/Settings/module grid; filter starts at first character.
  assert.match(nav, /const searching = searchOpen \|\| queryTrimmed\.length > 0/);
  assert.match(nav, /\{\!searching \? \(/);
  assert.match(nav, /onChangeText=\{setQuery\}/);
  // Same NewChatIcon component as chat header (compose square+pencil), smaller size only.
  assert.match(nav, /NewChatIcon/);
  assert.match(nav, /<NewChatIcon color=\{colors\.onAccent\} size=\{20\}/);
  assert.doesNotMatch(nav, /DRAWER_TOOL_ICONS\.newChat/);
  assert.match(drawer, /Keyboard\.dismiss/);
  assert.match(chat, /Keyboard\.dismiss/);
  assert.match(overlays, /<NavDrawer[\s\S]*onNewChat=/);

  const modules = read('features/nav/moduleIcons.ts');
  const headerIcons = read('features/chat/ChatHeaderIcons.tsx');
  const header = read('features/chat/ChatHeader.tsx');
  assert.match(modules, /NEW_CHAT_ICON\s*=\s*ion\('create-outline'\)/);
  assert.doesNotMatch(modules, /newChat:\s*feather\('plus'\)/);
  assert.match(headerIcons, /export function NewChatIcon/);
  assert.match(headerIcons, /NEW_CHAT_ICON/);
  assert.match(headerIcons, /AppIcon/);
  assert.match(header, /<NewChatIcon color=\{iconColor\}/);
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
