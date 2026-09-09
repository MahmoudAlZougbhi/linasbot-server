/**
 * Mobile design-handoff unit checks (no device required).
 * Run: node --test mobile/linas-ai/tests/*.test.mjs
 */
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import { readChatScreenBundle } from './chatScreenBundle.mjs';

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
  assert.match(text, /titleKey:\s*'navSmartFollowUp'/);
});

test('drawer Smart Follow-Up tile uses short Follow up labels', () => {
  const en = read('i18n/locales/smartFollowUpEn.ts');
  const ar = read('i18n/locales/smartFollowUpAr.ts');
  const fr = read('i18n/locales/smartFollowUpFr.ts');
  const grid = read('features/nav/DrawerNavGrid.tsx');
  assert.match(grid, /tr\(mod\.titleKey\)/);
  assert.match(en, /navSmartFollowUp:\s*'Follow up',/);
  assert.match(ar, /navSmartFollowUp:\s*'المتابعة',/);
  assert.match(fr, /navSmartFollowUp:\s*'Relance',/);
  assert.doesNotMatch(en, /navSmartFollowUp:\s*'Smart Follow-Up'/);
  assert.match(en, /sfuTitle:\s*'Follow up',/);
  assert.match(ar, /sfuTitle:\s*'المتابعة',/);
  assert.match(fr, /sfuTitle:\s*'Relance',/);
  assert.doesNotMatch(en, /sfuTitle:\s*'Smart Follow-Up'/);
});

test('drawer, Dashboard, and Settings use Smart Q&A product name', () => {
  const en = read('i18n/locales/en.ts');
  const ar = read('i18n/locales/ar.ts');
  const fr = read('i18n/locales/fr.ts');
  const dashEn = read('i18n/locales/dashboardEn.ts');
  const dashAr = read('i18n/locales/dashboardAr.ts');
  const dashFr = read('i18n/locales/dashboardFr.ts');
  const usersEn = read('i18n/locales/usersUiEn.ts');
  const usersAr = read('i18n/locales/usersUiAr.ts');
  const usersFr = read('i18n/locales/usersUiFr.ts');
  const faqEn = read('i18n/locales/faqUiEn.ts');
  const grid = read('features/nav/DrawerNavGrid.tsx');
  const drawer = read('features/nav/drawerModules.ts');
  assert.match(grid, /tr\(mod\.titleKey\)/);
  assert.match(drawer, /id:\s*'faq',\s*titleKey:\s*'faqTitle'/);
  assert.match(en, /faqTitle:\s*'Smart Q&A'/);
  assert.match(ar, /faqTitle:\s*'الأسئلة والأجوبة'/);
  assert.match(fr, /faqTitle:\s*'Q&R intelligentes'/);
  assert.match(dashEn, /dashSmartAnswers:\s*'Smart Q&A'/);
  assert.match(dashAr, /dashSmartAnswers:\s*'أسئلة وأجوبة'/);
  assert.match(dashFr, /dashSmartAnswers:\s*'Q&R intelligentes'/);
  assert.match(usersEn, /usersAccessSmartAnswers:\s*'Smart Q&A'/);
  assert.match(usersAr, /usersAccessSmartAnswers:\s*'الأسئلة والأجوبة'/);
  assert.match(usersFr, /usersAccessSmartAnswers:\s*'Q&R intelligentes'/);
  assert.match(faqEn, /faqLangPickerTitle:\s*'Smart Q&A languages'/);
  assert.doesNotMatch(en, /Smart Answers/);
  assert.doesNotMatch(dashEn, /Smart Answers/);
  assert.doesNotMatch(usersEn, /Smart Answers/);
  assert.doesNotMatch(faqEn, /Smart Answers/);
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
  assert.match(modules, /faq: feather\('help-circle'\)/);
  assert.match(modules, /livechat: feather\('message-square'\)/);
  assert.match(modules, /integrations: mci\('power-plug-outline'\)/);
  assert.match(modules, /subscription: feather\('credit-card'\)/);
  assert.match(modules, /settings: feather\('settings'\)/);
  assert.match(cm, /AiSetupHubSections/);
  assert.match(cmIcons, /ai_basics: mci\('robot-outline'\)/);
  assert.match(cmIcons, /languages: feather\('globe'\)/);
});

test('AI Setup hub hides care, handoff, and restricted topics', () => {
  const sections = read('features/cm/cmSections.ts');
  const cm = read('features/cm/CmScreen.tsx');
  for (const id of ['care', 'handoff', 'restricted']) {
    assert.match(sections, new RegExp(`id: '${id}'[\\s\\S]*?showInCmHub: false`));
  }
  assert.match(sections, /CM_HUB_PROGRESS_SECTION_IDS/);
  assert.match(sections, /CM_HUB_PROGRESS_EXCLUDED/);
  assert.match(cm, /summarizeHubProgress/);
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
  const chat = readChatScreenBundle(read);
  const controller = read('features/chat/useChatScreenController.ts');
  const mode = read('features/chat/ChatModeToggle.tsx');
  const session = read('features/chat/useChatSession.ts');
  assert.match(mode, /Segmented Chat \| Work/);
  assert.match(chat, /ChatModeToggle/);
  assert.match(controller, /hasUserMessage/);
  assert.match(controller, /showModeToggle/);
  assert.match(controller, /isAuthenticated && !hasUserMessage/);
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
  assert.doesNotMatch(appJson, /"buildNumber"/);
  assert.doesNotMatch(appJson, /"versionCode"/);
  assert.ok(existsSync(join(root, 'assets/splash-native.png')));
  assert.doesNotMatch(
    chat,
    /if \(loading\) \{\s*return \(\s*<GradientBackground>\s*<View style=\{styles\.center\}>/,
  );
  assert.match(chat, /c\.loading && c\.messages\.length === 0 \? \(/);
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
  const chat = readChatScreenBundle(read);
  const thinking = read('features/chat/ThinkingRow.tsx');
  assert.match(turn, /setThinking\(true\)/);
  assert.match(turn, /onDelta:[\s\S]*setThinking\(false\)/);
  assert.match(turn, /onError:[\s\S]*resetUi\(\)/);
  assert.match(footer, /thinking && !liveText/);
  assert.match(footer, /ThinkingRow/);
  assert.match(footer, /thinkingLabel/);
  assert.match(chat, /thinkingLabel=\{c\.tr\('chatThinking'\)\}/);
  assert.match(footer, /id: 'live-stream'/);
  assert.match(list, /thinking=\{thinking\}/);
  // Guest send also shows Thinking in the same footer slot.
  assert.match(chat, /thinking=\{c\.turn\.thinking \|\| \(!isAuthenticated && c\.guest\.sending\)\}/);
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
  const chat = readChatScreenBundle(read);
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
  assert.match(formData, /prepareUploadUri/);
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
  assert.doesNotMatch(composer, /formatVoiceElapsed/);
  assert.match(controls, /formatVoiceElapsed\(elapsedMs\)/);
  assert.match(controls, /timerBeside/);
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
