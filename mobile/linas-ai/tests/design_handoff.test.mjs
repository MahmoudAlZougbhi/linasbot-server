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
  const png = read('components/linasSparklePng.ts');
  const fade = read('features/nav/DrawerFadeSeparator.tsx');
  const pkg = readFileSync(join(root, 'package.json'), 'utf8');
  assert.match(sparkle, /SPARKLE_LIGHT_URI/);
  assert.match(sparkle, /SPARKLE_LIGHT_DEEP_URI/);
  assert.match(sparkle, /SPARKLE_DARK_URI/);
  assert.match(sparkle, /SPARKLE_DARK_DEEP_URI/);
  assert.match(sparkle, /sparkleSource\(color\)/);
  assert.match(png, /data:image\/png;base64,/);
  assert.doesNotMatch(sparkle, /tintColor/);
  assert.doesNotMatch(sparkle, /require\(/);
  assert.doesNotMatch(sparkle, /react-native-svg/);
  assert.doesNotMatch(fade, /react-native-svg/);
  assert.doesNotMatch(pkg, /react-native-svg/);
  assert.ok(existsSync(join(root, 'assets/linas-sparkle-template.png')));
  for (const name of [
    'linas-sparkle-light.png',
    'linas-sparkle-light-deep.png',
    'linas-sparkle-dark.png',
    'linas-sparkle-dark-deep.png',
  ]) {
    assert.ok(existsSync(join(root, 'assets', name)));
  }
});

test('drawer AI Setup active tile uses the same selected chrome as other modules', () => {
  const grid = read('features/nav/DrawerNavGrid.tsx');
  const header = read('features/nav/DrawerHeader.tsx');
  const fade = read('features/nav/DrawerFadeSeparator.tsx');
  assert.match(grid, /modId === 'cm'/);
  assert.match(grid, /const active = activeArea === mod\.id/);
  assert.match(grid, /const tileBg = active \? colors\.activeRow : 'transparent'/);
  assert.doesNotMatch(grid, /isAiSetup/);
  assert.doesNotMatch(grid, /aiSetupTile/);
  assert.doesNotMatch(grid, /featuredIconWrap/);
  assert.doesNotMatch(grid, /featuredIconShadow/);
  assert.doesNotMatch(grid, /colors\.mintSoft/);
  assert.doesNotMatch(grid, /colors\.accentSoft/);
  assert.match(grid, /LinasSparkleIcon[\s\S]*color=\{colors\.accentDeep\}/);
  assert.match(header, /LinasSparkleIcon size=\{20\} color=\{colors\.accentDeep\}/);
  assert.match(
    header,
    /DrawerFadeSeparator lineColor=\{colors\.accentDeep\} starColor=\{colors\.accentDeep\}/,
  );
  assert.match(fade, /SPARKLE_SIZE = 12/);
  assert.match(fade, /SPARKLE_GAP = 6/);
  assert.match(fade, /LINE_HEIGHT = 1/);
  assert.match(fade, /FADE_STEPS = 12/);
});

test('drawer AI Setup percent badge uses seafoam pill with white border', () => {
  const grid = read('features/nav/DrawerNavGrid.tsx');
  const tokens = read('theme/tokens.ts');
  assert.match(grid, /badge\.tone === 'teal'/);
  assert.match(grid, /backgroundColor:\s*colors\.accentMid/);
  assert.match(grid, /borderWidth:\s*1/);
  assert.match(grid, /borderColor:\s*'#FFFFFF'/);
  assert.match(grid, /badge\.tone === 'teal'\s*\?\s*\{\s*color:\s*'#FFFFFF'\s*\}/);
  assert.doesNotMatch(grid, /badge\.tone === 'teal'[\s\S]*?colors\.accentDeep/);
  assert.match(tokens, /accentMid:\s*'#4A9B8E'/);
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
  const tokens = read('features/boot/bootSplashTokens.ts');
  const index = readFileSync(join(root, 'index.ts'), 'utf8');
  const appJson = readFileSync(join(root, 'app.json'), 'utf8');
  const chat = read('features/chat/ChatScreen.tsx');
  const login = read('features/auth/LoginScreen.tsx');
  const authChrome = read('features/auth/AuthChrome.tsx');
  assert.match(boot, /splash-native\.png/);
  assert.match(boot, /bootSplashTokens/);
  assert.match(tokens, /background:\s*'#083A37'/);
  assert.match(tokens, /markSize:\s*220/);
  assert.match(tokens, /minDisplayMs:\s*900/);
  assert.match(tokens, /maxHoldMs:\s*2500/);
  assert.match(tokens, /exitFadeMs:\s*220/);
  assert.match(boot, /appReady/);
  assert.match(boot, /splashExitDelayMs/);
  assert.match(boot, /isReduceMotionEnabled|reduceMotionChanged/);
  assert.match(boot, /SplashScreen\.hideAsync/);
  assert.doesNotMatch(boot, /LinasAvatar/);
  assert.doesNotMatch(boot, /Opening Linas AI/);
  assert.doesNotMatch(boot, /progressTrack/);
  assert.doesNotMatch(boot, /BootSplashAiLine/);
  assert.doesNotMatch(boot, /Linas AI/);
  assert.equal(existsSync(join(root, 'src/features/boot/BootSplashAiLine.tsx')), false);
  assert.match(index, /preventAutoHideAsync/);
  assert.match(appJson, /"backgroundColor":\s*"#083A37"/);
  assert.match(appJson, /"imageWidth":\s*220/);
  assert.match(appJson, /splash-native\.png/);
  assert.doesNotMatch(appJson, /#FBFAFA/);
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
  assert.match(login, /AuthChrome/);
  assert.match(authChrome, /LinasSparkleIcon/);
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
  const styles = read('features/chat/composerStyles.ts');
  const height = read('features/chat/composerInputHeight.ts');
  const autoGrow = read('features/chat/useComposerInputAutoGrow.ts');
  const en = read('i18n/locales/en.ts');
  assert.match(composer, /styles\.pill/);
  assert.match(composer, /PlusCircleGlyph/);
  assert.match(composer, /SendArrowGlyph/);
  assert.match(composer, /sendInside/);
  assert.match(composer, /scrollEnabled=\{atMaxHeight\}/);
  assert.match(composer, /composerPlaceholderChat/);
  assert.match(composer, /composerPlaceholderWork/);
  assert.match(styles, /minHeight:\s*COMPOSER_PILL_MIN_H/);
  assert.match(styles, /justifyContent:\s*'center'/);
  assert.match(styles, /direction:\s*'ltr'/);
  assert.match(height, /COMPOSER_PILL_MIN_H = 44/);
  assert.match(height, /COMPOSER_INPUT_MAX_LINES = 8/);
  assert.match(height, /COMPOSER_INPUT_MAX_H =/);
  assert.match(autoGrow, /debounceComposerHeight/);
  assert.match(en, /composerPlaceholderChat:\s*'Chat with Linas'/);
  assert.match(en, /composerPlaceholderWork:\s*'Work with Linas'/);
  assert.match(composer, /placeholder=\{placeholder\}/);
  assert.match(composer, /pillStacked/);
  assert.match(styles, /actionRow/);
});

test('Live Chat inbox matches design handoff (search, All/Human, platform row)', () => {
  const screen = read('features/livechat/LiveChatScreen.tsx');
  const inbox = read('features/livechat/LiveChatInbox.tsx');
  const search = read('features/livechat/InboxSearchBar.tsx');
  const pills = read('features/livechat/InboxFilterPills.tsx');
  const chips = read('features/livechat/InboxChannelChips.tsx');
  const row = read('features/livechat/ConversationRow.tsx');
  const icon = read('features/livechat/PlatformChannelIcon.tsx');
  const types = read('features/livechat/liveChatTypes.ts');
  const thread = read('features/livechat/LiveChatThread.tsx');
  assert.match(screen, /subtitle="All customer conversations"/);
  assert.match(search, /borderRadius:\s*radii\.pill/);
  assert.match(search, /placeholder="Search conversations"/);
  assert.doesNotMatch(search, /feather\('filter'\)/);
  assert.match(pills, /label:\s*'All'/);
  assert.match(pills, /label:\s*'Human'/);
  assert.match(pills, /id:\s*'with_operator'/);
  assert.match(pills, /colors\.accentSoft/);
  assert.match(pills, /active \? colors\.text : colors\.textMuted/);
  assert.doesNotMatch(pills, /Waiting|Closed/);
  assert.match(chips, /id: 'whatsapp'/);
  assert.match(chips, /id: 'instagram'/);
  assert.match(chips, /id: 'facebook'/);
  assert.match(chips, /id: 'tiktok'/);
  assert.match(row, /PlatformChannelIcon/);
  assert.match(row, /assigneeLabel/);
  assert.match(row, /unread/);
  assert.match(row, /colors\.accentDeep/);
  assert.match(icon, /logo-whatsapp/);
  assert.match(icon, /logo-instagram/);
  assert.match(icon, /facebook-messenger/);
  assert.match(icon, /logo-tiktok/);
  assert.match(types, /hour12:\s*true/);
  assert.match(thread, /LiveChatComposer/);
  assert.match(thread, /LiveChatAssignSheet/);
  assert.match(thread, /onTakeover/);
  assert.doesNotMatch(thread, /Read-only/);
});

test('drawer search chrome is header icon; Settings beside search; New chat on Recent row', () => {
  const nav = read('features/nav/NavDrawer.tsx');
  const drawerHeader = read('features/nav/DrawerHeader.tsx');
  const recents = read('features/nav/DrawerRecents.tsx');
  const chat = read('features/chat/ChatScreen.tsx');
  const overlays = read('features/chat/ChatScreenOverlays.tsx');
  const drawer = read('components/SideDrawer.tsx');
  assert.doesNotMatch(nav, /DrawerFooter/);
  assert.match(drawerHeader, /DRAWER_TOOL_ICONS\.search/);
  assert.match(drawerHeader, /DRAWER_TOOL_ICONS\.settings/);
  assert.match(drawerHeader, /onOpenSettings/);
  assert.match(drawerHeader, /headerActions/);
  assert.match(drawerHeader, /DrawerFadeSeparator/);
  assert.match(drawerHeader, /searchConversationTitles/);
  assert.match(recents, /NEW_CHAT_ICON/);
  assert.match(recents, /onNewChat/);
  assert.match(recents, /headingRow/);
  assert.doesNotMatch(recents, /tr\('newChat'\)[\s\S]*Text/);
  assert.match(nav, /noChatsMatch/);
  assert.match(nav, /emptyLabel/);
  const configSrc = read('config.ts');
  assert.match(configSrc, /Constants\.expoConfig\?\.version/);
  assert.match(configSrc, /APP_VERSION_LABEL/);
  assert.match(configSrc, /APP_BUILD_LABEL/);
  const settings = read('features/settings/SettingsScreen.tsx');
  const settingsChrome = read('features/settings/SettingsChrome.tsx');
  const settingsEn = read('i18n/locales/settingsUiEn.ts');
  assert.match(settings, /APP_VERSION/);
  assert.match(settings, /APP_BUILD_LABEL/);
  assert.match(settings, /SettingsFooter version=\{APP_VERSION\} build=\{APP_BUILD_LABEL\}/);
  assert.match(settingsChrome, /settingsVersionFooter/);
  assert.match(settingsEn, /Linas AI • Version \{version\} \(\{build\}\)/);
  // EAS: remote version source + autoIncrement so each TF/store ship bumps build without a commit.
  const easJson = readFileSync(join(root, 'eas.json'), 'utf8');
  assert.match(easJson, /"appVersionSource":\s*"remote"/);
  assert.match(easJson, /"production"[\s\S]*"autoIncrement":\s*true/);
  assert.match(easJson, /"testflight"[\s\S]*"autoIncrement":\s*true/);
  assert.match(drawerHeader, /wordmark/);
  assert.match(drawerHeader, /DrawerFadeSeparator/);
  // Search mode hides module grid; filter starts at first character.
  assert.match(nav, /const searching = searchOpen \|\| queryTrimmed\.length > 0/);
  assert.match(nav, /\{\!searching \? \(/);
  assert.match(nav, /onChangeQuery=\{setQuery\}|onChangeText=\{setQuery\}/);
  assert.match(recents, /NEW_CHAT_ICON/);
  assert.match(recents, /accessibilityLabel=\{tr\('newChat'\)\}/);
  assert.doesNotMatch(recents, /newChatBtn/);
  // No footer dock / bottom padding strip — Recents fills to the screen bottom.
  assert.match(drawer, /paddingBottom:\s*0/);
  assert.match(drawer, /height/);
  assert.match(drawer, /styles\.body/);
  assert.doesNotMatch(drawer, /paddingBottom:\s*Math\.max\(insets\.bottom/);
  assert.doesNotMatch(drawer, /insets\.bottom\s*\+\s*12/);
  assert.doesNotMatch(nav, /DRAWER_TOOL_ICONS\.newChat/);
  assert.match(drawer, /Keyboard\.dismiss/);
  assert.match(drawer, /pointerEvents=\{hitActive/);
  assert.match(drawer, /DRAWER_CLOSE_MS/);
  assert.match(chat, /Keyboard\.dismiss/);
  assert.match(chat, /composerInputRef\.current\?\.blur\(\)/);
  assert.doesNotMatch(chat, /<ChatComposer[\s\S]*?autoFocus/);
  assert.match(overlays, /<NavDrawer[\s\S]*onNewChat=/);

  const modules = read('features/nav/moduleIcons.ts');
  assert.match(modules, /NEW_CHAT_ICON\s*=\s*ion\('create-outline'\)/);
  assert.doesNotMatch(modules, /newChat:\s*feather\('plus'\)/);
});

test('Settings hosts AI Limits only (no Actions)', () => {
  const settings = read('features/settings/SettingsScreen.tsx');
  const tree = read('app/AppScreenTree.tsx');
  assert.match(settings, /onOpenAiLimits/);
  assert.match(settings, /settingsAiLimits/);
  assert.doesNotMatch(settings, /SettingsAboutSheet/);
  assert.doesNotMatch(settings, /settingsAboutLinas/);
  assert.doesNotMatch(settings, /onOpenActions/);
  assert.doesNotMatch(settings, /settingsActions/);
  assert.doesNotMatch(tree, /section: 'actions'/);
  assert.match(tree, /section: 'ai_limits'/);
  assert.match(tree, /backTo: 'settings'/);
});

test('Settings hosts Notifications and Logout; drawer does not', () => {
  const settings = read('features/settings/SettingsScreen.tsx');
  const chrome = read('features/settings/SettingsChrome.tsx');
  const nav = read('features/nav/NavDrawer.tsx');
  const chat = read('features/chat/ChatScreen.tsx');
  const tree = read('app/AppScreenTree.tsx');
  assert.match(settings, /onOpenNotifications/);
  assert.match(settings, /notificationsTitle/);
  assert.match(settings, /SettingsLogoutButton/);
  assert.match(settings, /onLogout/);
  assert.match(chrome, /tr\('logout'\)/);
  assert.doesNotMatch(nav, /onOpenNotifications/);
  assert.doesNotMatch(nav, /onLogout/);
  assert.doesNotMatch(nav, /Notifications/);
  assert.doesNotMatch(nav, /Log out/);
  assert.doesNotMatch(chat, /onLogout/);
  assert.match(tree, /onOpenNotifications=\{\(\) => setScreen\(\{ name: 'notifications', backTo: 'settings' \}\)\}/);
});

test('Settings does not duplicate AI Basics CM store', () => {
  const settings = read('features/settings/SettingsScreen.tsx');
  const chrome = read('features/settings/SettingsChrome.tsx');
  assert.doesNotMatch(settings, /settingsBusinessProfile/);
  assert.doesNotMatch(settings, /settingsLinkApple/);
  assert.doesNotMatch(settings, /settingsUnlinkApple/);
  assert.doesNotMatch(settings, /MFA/);
  assert.doesNotMatch(settings, /Passkey/);
  assert.doesNotMatch(chrome, /MFA/);
  const en = read('i18n/locales/en.ts');
  assert.doesNotMatch(en, /Open AI Setup → AI Basics/);
  assert.doesNotMatch(en, /settingsBusinessProfile/);
});

test('Integrations header refresh is customer-facing', () => {
  const integ = read('features/integrations/IntegrationsScreen.tsx');
  assert.match(integ, /IntegrationRefreshButton/);
  assert.match(integ, /tr\('refreshConnectionStatus'\)/);
  assert.doesNotMatch(integ, /refreshConnectionStatusHint/);
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

test('chat AI replies use larger regular body; user bubble stays 16px', () => {
  const typography = read('theme/typography.ts');
  const bubble = read('features/chat/ChatBubble.tsx');
  const aiBody = read('features/chat/AiMessageBody.tsx');
  assert.match(typography, /chatAi:[\s\S]*?fontSize:\s*17/);
  assert.match(typography, /chatAi:[\s\S]*?lineHeight:\s*24/);
  assert.match(typography, /chatAi:[\s\S]*?fontWeight:\s*'400'/);
  assert.match(typography, /chatUser:[\s\S]*?fontSize:\s*16/);
  assert.match(typography, /chatUser:[\s\S]*?lineHeight:\s*23/);
  assert.match(bubble, /textUser:[\s\S]*?typography\.chatUser/);
  assert.match(bubble, /textAi:[\s\S]*?typography\.chatAi/);
  assert.doesNotMatch(bubble, /textUser:[\s\S]*?fontSize:\s*1[0-5]/);
  assert.match(aiBody, /line:\s*\{[\s\S]*?typography\.chatAi/);
  assert.doesNotMatch(aiBody, /line:\s*\{[^}]*bodyMedium/);
  assert.doesNotMatch(aiBody, /sectionTitle:[\s\S]*?fontSize:\s*1[0-5]/);
});

test('no bottom tab navigator wiring', () => {
  const app = readFileSync(join(root, 'App.tsx'), 'utf8');
  const shell = read('app/AppShell.tsx');
  const tree = read('app/AppScreenTree.tsx');
  assert.doesNotMatch(app, /createBottomTabNavigator|BottomTab|Tab\.Navigator/);
  assert.doesNotMatch(shell, /createBottomTabNavigator|BottomTab|Tab\.Navigator/);
  assert.doesNotMatch(tree, /createBottomTabNavigator|BottomTab|Tab\.Navigator/);
});

test('Subscription current plan matches design handoff', () => {
  const current = read('features/billing/CurrentPlanScreen.tsx');
  const hero = read('features/billing/CurrentPlanHeroCard.tsx');
  const chrome = read('features/shared/ScreenChrome.tsx');
  const billing = read('features/billing/BillingScreen.tsx');
  assert.match(billing, /navSubscription/);
  assert.match(billing, /subCurrentSubtitle/);
  assert.match(chrome, /MenuIcon/);
  assert.match(hero, /subCurrentPlanKicker/);
  assert.match(hero, /subAvailableCredits/);
  assert.match(hero, /subBuyCredits/);
  assert.match(current, /subWhatIncludes/);
  assert.match(current, /SmartAnswersInfo/);
  assert.match(current, /PlanNotIncluded/);
  assert.match(current, /subUpgradePlan/);
  assert.match(current, /subCreditsRefreshNote/);
  assert.match(hero, /borderColor:\s*colors\.accent/);
});

test('Subscription choose-a-plan matches design handoff', () => {
  const choose = read('features/billing/ChoosePlanScreen.tsx');
  const chips = read('features/billing/PlanChipRow.tsx');
  const detail = read('features/billing/PlanDetailCard.tsx');
  const toggle = read('features/billing/BillingPeriodToggle.tsx');
  const billing = read('features/billing/BillingScreen.tsx');
  assert.match(billing, /subChooseTitle/);
  assert.match(billing, /onBack/);
  assert.match(choose, /BillingPeriodToggle/);
  assert.match(choose, /PlanChipRow/);
  assert.match(choose, /PlanDetailCard/);
  assert.match(choose, /subCtaChooseLite|PLAN_CHOOSE_CTA/);
  assert.match(chips, /PLAN_ORDER\.map/);
  assert.match(chips, /subYourPlan/);
  assert.match(chips, /subTapToCompare/);
  assert.match(toggle, /subPeriodMonthly/);
  assert.match(toggle, /subPeriodYearly/);
  assert.match(toggle, /borderColor:\s*active \? colors\.accent/);
  assert.match(detail, /PLAN_BADGE_KEY/);
  assert.match(detail, /LinasSparkleIcon/);
  assert.match(detail, /subAiCreditsIncluded/);
  assert.match(detail, /SmartAnswersInfo/);
});

test('Buy credits sheet matches design handoff', () => {
  const sheet = read('features/billing/BuyCreditsSheet.tsx');
  const en = read('i18n/locales/subscriptionEn.ts');
  assert.match(sheet, /subBuyCredits/);
  assert.match(sheet, /subChooseCreditPack/);
  assert.match(sheet, /accessibilityRole="radio"/);
  assert.match(sheet, /DEFAULT_CREDIT_PACK/);
  assert.match(sheet, /subBuyCreditsCta/);
  assert.match(sheet, /subPurchasedNoExpire/);
  assert.match(sheet, /subFooterStore/);
  assert.match(sheet, /subCancel/);
  assert.match(en, /Buy \{n\} credits • \{price\}/);
  assert.match(en, /Payment is completed securely through the App Store or Google Play/);
  assert.match(en, /Purchased credits do not expire/);
});

test('Customer AI Limits screen matches design handoff', () => {
  const editor = read('features/cm/editors/AiLimitsEditor.tsx');
  const field = read('features/cm/editors/AiLimitsPencilField.tsx');
  const screen = read('features/cm/CmSectionScreen.tsx');
  const en = read('i18n/locales/aiSetupEn.ts');
  const ar = read('i18n/locales/aiSetupAr.ts');
  const fr = read('i18n/locales/aiSetupFr.ts');
  assert.match(screen, /tr\('aiLimitsTitle'\)/);
  assert.match(screen, /tr\('aiLimitsSubtitle'\)/);
  assert.match(editor, /aiLimitsBanner/);
  assert.match(editor, /aiLimitsTextChat/);
  assert.match(editor, /aiLimitsPhotos/);
  assert.match(editor, /aiLimitsVoice/);
  assert.match(editor, /aiLimitsReadPerMessage/);
  assert.match(editor, /aiLimitsPhotosPerMessage/);
  assert.match(editor, /aiLimitsMinutesPerMessage/);
  assert.match(editor, /text_replies_per_day/);
  assert.match(editor, /image_per_month/);
  assert.match(editor, /voice_minutes_per_month/);
  assert.match(editor, /aiLimitsAutoTitle/);
  assert.match(editor, /aiLimitsSave/);
  assert.match(editor, /aiLimitsApplyNow/);
  assert.match(field, /feather\('edit-2'\)/);
  assert.doesNotMatch(editor, /human_handoff_enabled/);
  assert.doesNotMatch(editor, /TikTok/);
  assert.match(en, /Customer AI Limits/);
  assert.match(en, /Protect credits by limiting each customer/);
  assert.match(ar, /حدود الذكاء الاصطناعي للزبائن/);
  assert.match(fr, /Limites IA clients/);
});
