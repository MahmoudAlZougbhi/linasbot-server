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

test('brand sparkle renders without react-native-svg (no Uni placeholder)', () => {
  const sparkle = read('components/LinasSparkleIcon.tsx');
  const fade = read('features/nav/DrawerFadeSeparator.tsx');
  const pkg = readFileSync(join(root, 'package.json'), 'utf8');
  assert.match(sparkle, /linas-sparkle-template\.png/);
  assert.match(sparkle, /tintColor:\s*color/);
  assert.doesNotMatch(sparkle, /react-native-svg/);
  assert.doesNotMatch(fade, /react-native-svg/);
  assert.doesNotMatch(pkg, /react-native-svg/);
  assert.ok(existsSync(join(root, 'assets/linas-sparkle-template.png')));
});

test('drawer AI Setup active tile uses mint sparkle chrome', () => {
  const grid = read('features/nav/DrawerNavGrid.tsx');
  const header = read('features/nav/DrawerHeader.tsx');
  assert.match(grid, /modId === 'cm'/);
  assert.match(grid, /colors\.mintSoft/);
  assert.match(grid, /LinasSparkleIcon[\s\S]*color=\{colors\.accentDeep\}/);
  assert.match(header, /LinasSparkleIcon size=\{16\} color=\{colors\.text\}/);
});

test('drawer module order matches binding product order', () => {
  const text = read('features/nav/drawerModules.ts');
  // AI Setup (cm) is featured separately; grid order is DRAWER_MODULES only.
  assert.match(text, /export const FEATURED_AI_SETUP[\s\S]*?id:\s*'cm'/);
  const gridBlock = text.match(/export const DRAWER_MODULES: DrawerModule\[] = \[([\s\S]*?)\];/);
  assert.ok(gridBlock, 'DRAWER_MODULES array missing');
  assert.doesNotMatch(gridBlock[1], /id:\s*'cm'/);
  const ids = [...gridBlock[1].matchAll(/id:\s*'([^']+)'/g)].map((m) => m[1]);
  assert.deepEqual(ids, [
    'dashboard',
    'smartFollowUp',
    'faq',
    'livechat',
    'requests',
    'integrations',
    'users',
    'subscription',
  ]);
});

test('drawer and CM module tiles expose design handoff icons', () => {
  const grid = read('features/nav/DrawerNavGrid.tsx');
  const modules = read('features/nav/moduleIcons.ts');
  const cm = read('features/cm/CmScreen.tsx');
  const cmIcons = read('features/cm/cmSectionIcons.ts');
  assert.match(grid, /MODULE_ICONS/);
  assert.match(grid, /AppIcon/);
  assert.match(modules, /dashboard: feather\('grid'\)/);
  assert.match(modules, /cm: ion\('sparkles-outline'\)/);
  assert.match(modules, /livechat: feather\('message-square'\)/);
  assert.match(modules, /integrations: mci\('power-plug-outline'\)/);
  assert.match(modules, /subscription: feather\('credit-card'\)/);
  assert.match(modules, /settings: feather\('settings'\)/);
  assert.match(cm, /AiSetupSectionGrid/);
  assert.match(cmIcons, /ai_basics: mci\('robot-outline'\)/);
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

test('New Chat welcome types the greeting seed (no empty-state typewriter kill)', () => {
  const empty = read('features/chat/OwnerEmptyState.tsx');
  const typewriter = read('features/chat/useWelcomeTypewriter.ts');
  const bubble = read('features/chat/ChatBubble.tsx');
  const session = read('features/chat/useChatSession.ts');
  const chat = read('features/chat/ChatScreen.tsx');
  assert.doesNotMatch(empty, /useWelcomeTypewriter|useOnceTypewriter/);
  assert.match(typewriter, /useOnceTypewriter/);
  assert.doesNotMatch(typewriter, /holdFull|deleteBody|deleteTitle/);
  assert.match(bubble, /useOnceTypewriter/);
  assert.match(bubble, /useReduceMotion/);
  assert.match(session, /seedTypewriterMessageId/);
  assert.match(chat, /seedTypewriterMessageId/);
  assert.match(chat, /clearSeedTypewriter/);
});

test('App launches chat-first for guest and owner', () => {
  const app = readFileSync(join(root, 'App.tsx'), 'utf8');
  const shell = read('app/AppShell.tsx');
  assert.match(app, /AppShell/);
  assert.match(shell, /setScreen\(\{ name: 'chat' \}\)/);
  assert.doesNotMatch(app, /name: 'creative'/);
  assert.doesNotMatch(app, /CreativeStudio/);
  assert.doesNotMatch(shell, /CreativeStudio/);
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
  // Native splash must stay logo-free (solid emerald) so Android 12+ does not
  // circular-mask splash-icon into a different first shape before BootSplash.
  assert.match(boot, /splash-native|solid emerald|no logo/i);
  assert.match(index, /preventAutoHideAsync/);
  assert.match(appJson, /"backgroundColor":\s*"#0B3D34"/);
  assert.match(appJson, /splash-native\.png/);
  assert.doesNotMatch(
    appJson,
    /expo-splash-screen[\s\S]*"image":\s*"\.\/assets\/splash-icon\.png"/,
  );
  assert.match(appJson, /"bundleIdentifier":\s*"com\.linasai\.app"/);
  assert.match(appJson, /"package":\s*"com\.linasai\.app"/);
  assert.match(appJson, /expo-audio/);
  assert.match(appJson, /"buildNumber":\s*"23"/);
  assert.match(appJson, /"versionCode":\s*23/);
  assert.ok(existsSync(join(root, 'assets/splash-native.png')));
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
  assert.match(footer, /thinkingLabel/);
  assert.match(chat, /thinkingLabel=\{tr\('chatThinking'\)\}/);
  assert.match(footer, /id: 'live-stream'/);
  assert.match(list, /thinking=\{thinking\}/);
  // Guest send also shows Thinking in the same footer slot.
  assert.match(chat, /thinking=\{turn\.thinking \|\| \(!isAuthenticated && guest\.sending\)\}/);
  assert.match(thinking, /isReduceMotionEnabled|reduceMotionChanged/);
  assert.match(thinking, /LinasStarMark/);
});

test('proposal card exposes complete V2 actions beyond Review/Discard', () => {
  const card = read('features/chat/v2/ProposalCard.tsx');
  for (const key of [
    'proposalApprove',
    'proposalReviewInSetup',
    'proposalCancel',
    'proposalEdit',
    'proposalCurrent',
    'proposalProposed',
    'proposalNotAppliedYet',
  ]) {
    assert.match(card, new RegExp(`tr\\('${key}'\\)`));
  }
  const en = read('i18n/locales/en.ts');
  assert.match(en, /proposalApprove:\s*'Approve'/);
  assert.match(en, /proposalReviewInSetup:\s*'Review in AI Setup'/);
  assert.match(en, /proposalCancel:\s*'Cancel'/);
  assert.match(en, /proposalCurrent:\s*'Current'/);
  assert.match(en, /proposalProposed:\s*'Proposed'/);
  assert.match(en, /proposalNotAppliedYet:\s*'Not applied yet/);
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
  assert.match(chat, /appendVoiceTranscript\(prev, text\)/);
  assert.match(chat, /setDraft/);
  assert.match(chat, /showMic=\{isAuthenticated\}/);
  assert.match(chat, /onResumeVoice/);
  assert.match(chat, /onConfirmVoice/);
  assert.match(chat, /onDiscardVoice/);
  assert.match(composer, /showVoiceControl/);
  // Mic stays available with typed draft so confirm can append, not replace.
  assert.match(composer, /showMic && onToggleVoice && !streamingStop/);
  assert.doesNotMatch(composer, /voiceBusy \|\| !canSend/);
  assert.match(composer, /tr\('composerListening'\)/);
  assert.match(composer, /tr\('composerPaused'\)/);
  assert.match(composer, /tr\('composerTranscribing'\)/);
  assert.match(composer, /formatVoiceElapsed/);
  assert.match(composer, /StopGlyph/);
  const en = read('i18n/locales/en.ts');
  assert.match(en, /composerListening:\s*'Listening…'/);
  assert.match(en, /composerPaused:\s*'Paused'/);
  assert.match(en, /composerTranscribing:\s*'Transcribing…'/);
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
  const chip = read('features/chat/ComposerModelChip.tsx');
  const sheet = read('features/chat/LinEffortSheet.tsx');
  const chat = read('features/chat/ChatScreen.tsx');
  const mode = read('features/chat/ownerChatMode.ts');
  assert.match(composer, /onOwnerModeChange/);
  assert.match(composer, /LinEffortSheet/);
  assert.match(composer, /ComposerModelChip/);
  assert.match(chip, /accessibilityRole="button"/);
  assert.match(sheet, /linEffortLow/);
  assert.match(sheet, /linEffortHigh/);
  assert.match(sheet, /linEffortFast/);
  assert.match(sheet, /linEffortHighSub/);
  assert.match(sheet, /id: 'chat'/);
  assert.match(sheet, /id: 'work'/);
  assert.match(chat, /onOwnerModeChange=\{setOwnerMode\}/);
  assert.match(mode, /effortLabelForMode/);
});

test('composer bar matches design handoff (pill, grow, placeholders)', () => {
  const composer = read('features/chat/ChatComposer.tsx');
  const autoGrow = read('features/chat/useComposerInputAutoGrow.ts');
  const en = read('i18n/locales/en.ts');
  assert.match(composer, /styles\.pill/);
  assert.match(composer, /PlusCircleGlyph/);
  assert.match(composer, /SendArrowGlyph/);
  assert.match(composer, /sendOutside/);
  assert.match(composer, /scrollEnabled=\{atMaxHeight\}/);
  assert.match(composer, /composerPlaceholderChat/);
  assert.match(composer, /composerPlaceholderWork/);
  assert.match(autoGrow, /COMPOSER_INPUT_MAX_LINES = 8/);
  assert.match(autoGrow, /COMPOSER_INPUT_MAX_H = COMPOSER_INPUT_LINE_HEIGHT \* COMPOSER_INPUT_MAX_LINES/);
  assert.match(en, /composerPlaceholderChat:\s*'Chat with Linas'/);
  assert.match(en, /composerPlaceholderWork:\s*'Work with Linas'/);
});

test('Live Chat thread remains read-only', () => {
  const thread = read('features/livechat/LiveChatThread.tsx');
  assert.match(thread, /read-only/i);
  assert.match(thread, /StatusChip label="Read-only"/);
  assert.doesNotMatch(thread, /LiveChatComposer/);
  assert.doesNotMatch(thread, /onSendMessage/);
  assert.doesNotMatch(thread, /function\s+takeover|pauseAi|humanTakeover/i);
});

test('drawer search chrome is header icon; New chat + Settings in footer dock', () => {
  const nav = read('features/nav/NavDrawer.tsx');
  const drawerHeader = read('features/nav/DrawerHeader.tsx');
  const footer = read('features/nav/DrawerFooter.tsx');
  const chat = read('features/chat/ChatScreen.tsx');
  const overlays = read('features/chat/ChatScreenOverlays.tsx');
  const drawer = read('components/SideDrawer.tsx');
  assert.match(nav, /DrawerFooter/);
  assert.match(footer, /newChatBtn/);
  assert.match(footer, /settingsBtn/);
  assert.match(drawerHeader, /DRAWER_TOOL_ICONS\.search/);
  assert.match(drawerHeader, /DrawerFadeSeparator/);
  assert.match(drawerHeader, /searchConversationTitles/);
  assert.match(nav, /noChatsMatch/);
  assert.match(nav, /emptyLabel/);
  assert.match(footer, /APP_VERSION_LABEL/);
  const configSrc = read('config.ts');
  assert.match(configSrc, /Constants\.expoConfig\?\.version/);
  assert.match(configSrc, /APP_VERSION_LABEL/);
  assert.match(configSrc, /APP_BUILD_LABEL/);
  const settings = read('features/settings/SettingsScreen.tsx');
  assert.match(settings, /APP_VERSION/);
  assert.match(settings, /APP_BUILD_LABEL/);
  assert.match(settings, /build \{APP_BUILD_LABEL\}/);
  // EAS: remote version source + autoIncrement so each TF/store ship bumps build without a commit.
  const easJson = readFileSync(join(root, 'eas.json'), 'utf8');
  assert.match(easJson, /"appVersionSource":\s*"remote"/);
  assert.match(easJson, /"production"[\s\S]*"autoIncrement":\s*true/);
  assert.match(easJson, /"testflight"[\s\S]*"autoIncrement":\s*true/);
  // Version centered below action row; New Chat is wide pill + Settings circle.
  assert.match(footer, /textAlign:\s*'center'/);
  assert.match(footer, /styles\.actionRow[\s\S]*newChatBtn[\s\S]*settingsBtn/);
  assert.match(footer, /APP_VERSION_LABEL/);
  assert.match(drawerHeader, /wordmark/);
  assert.match(drawerHeader, /DrawerFadeSeparator/);
  // Search mode hides module grid; filter starts at first character.
  assert.match(nav, /const searching = searchOpen \|\| queryTrimmed\.length > 0/);
  assert.match(nav, /\{\!searching \? \(/);
  assert.match(nav, /onChangeQuery=\{setQuery\}|onChangeText=\{setQuery\}/);
  assert.match(footer, /NewChatIcon/);
  assert.match(footer, /<NewChatIcon color=\{colors\.onAccent\} size=\{16\}/);
  assert.match(footer, /tr\('newChat'\)/);
  assert.match(footer, /minHeight:\s*40/);
  // Dock sits on safe area only — no extra lift above the home indicator.
  assert.match(drawer, /paddingBottom:\s*Math\.max\(insets\.bottom,\s*4\)/);
  assert.doesNotMatch(drawer, /insets\.bottom\s*\+\s*12/);
  assert.doesNotMatch(nav, /DRAWER_TOOL_ICONS\.newChat/);
  assert.doesNotMatch(footer, /DRAWER_TOOL_ICONS\.newChat/);
  assert.match(drawer, /Keyboard\.dismiss/);
  assert.match(drawer, /pointerEvents=\{hitActive/);
  assert.match(drawer, /DRAWER_CLOSE_MS/);
  assert.match(chat, /Keyboard\.dismiss/);
  assert.match(chat, /composerInputRef\.current\?\.blur\(\)/);
  assert.doesNotMatch(chat, /<ChatComposer[\s\S]*?autoFocus/);
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

test('Settings hosts AI Limits only (no Actions)', () => {
  const settings = read('features/settings/SettingsScreen.tsx');
  const tree = read('app/AppScreenTree.tsx');
  assert.match(settings, /onOpenAiLimits/);
  assert.doesNotMatch(settings, /onOpenActions/);
  assert.doesNotMatch(settings, /settingsActions/);
  assert.doesNotMatch(tree, /section: 'actions'/);
});

test('Settings hosts Notifications and Logout; drawer does not', () => {
  const settings = read('features/settings/SettingsScreen.tsx');
  const nav = read('features/nav/NavDrawer.tsx');
  const chat = read('features/chat/ChatScreen.tsx');
  const tree = read('app/AppScreenTree.tsx');
  assert.match(settings, /onOpenNotifications/);
  assert.match(settings, /notificationsTitle/);
  assert.match(settings, /tr\('logout'\)/);
  assert.doesNotMatch(nav, /onOpenNotifications/);
  assert.doesNotMatch(nav, /onLogout/);
  assert.doesNotMatch(nav, /Notifications/);
  assert.doesNotMatch(nav, /Log out/);
  assert.doesNotMatch(chat, /onLogout/);
  assert.match(tree, /onOpenNotifications=\{\(\) => setScreen\(\{ name: 'notifications', backTo: 'settings' \}\)\}/);
});

test('Settings does not duplicate AI Basics CM store', () => {
  const settings = read('features/settings/SettingsScreen.tsx');
  assert.match(settings, /settingsBusinessProfileNote/);
  assert.doesNotMatch(settings, /MFA/);
  assert.doesNotMatch(settings, /Passkey/);
  const en = read('i18n/locales/en.ts');
  assert.match(en, /Open AI Setup → AI Basics/);
});

test('Integrations refresh is customer-facing and IG/FB only', () => {
  const integ = read('features/integrations/IntegrationsScreen.tsx');
  assert.match(integ, /tr\('refreshConnectionStatus'\)/);
  assert.match(integ, /tr\('refreshConnectionStatusHint'\)/);
  assert.doesNotMatch(integ, /App A only/);
  assert.doesNotMatch(integ, /webhooks/);
  assert.match(integ, /platform === 'instagram' \|\| row\.platform === 'facebook'/);
});

test('theme tokens include light and dark parity keys', () => {
  const tokens = read('theme/tokens.ts');
  assert.match(tokens, /export const lightColors/);
  assert.match(tokens, /export const darkColors/);
  assert.match(tokens, /accent: '#008B8B'/);
});

test('no bottom tab navigator wiring', () => {
  const app = readFileSync(join(root, 'App.tsx'), 'utf8');
  const shell = read('app/AppShell.tsx');
  const tree = read('app/AppScreenTree.tsx');
  assert.doesNotMatch(app, /createBottomTabNavigator|BottomTab|Tab\.Navigator/);
  assert.doesNotMatch(shell, /createBottomTabNavigator|BottomTab|Tab\.Navigator/);
  assert.doesNotMatch(tree, /createBottomTabNavigator|BottomTab|Tab\.Navigator/);
});
