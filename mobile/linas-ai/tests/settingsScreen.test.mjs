/**
 * Settings iOS handoff — sections, copy, logout, version, existing destinations.
 */
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

test('Settings handoff sections and rows match the iOS mock', () => {
  const screen = read('features/settings/SettingsScreen.tsx');
  const chrome = read('features/settings/SettingsChrome.tsx');
  const shell = read('features/shared/ScreenChrome.tsx');
  const tree = read('app/AppScreenTree.tsx');
  const en = read('i18n/locales/settingsUiEn.ts');
  const ar = read('i18n/locales/settingsUiAr.ts');
  const fr = read('i18n/locales/settingsUiFr.ts');
  const enAll = read('i18n/locales/en.ts');
  const arAll = read('i18n/locales/ar.ts');
  const frAll = read('i18n/locales/fr.ts');

  assert.match(screen, /groupAccount/);
  assert.match(screen, /settingsPreferences/);
  assert.match(screen, /settingsSupportLegal/);
  assert.match(screen, /settingsChangeName/);
  assert.match(screen, /changeEmail/);
  assert.match(screen, /notificationsTitle/);
  assert.match(screen, /settingsNotificationsHint/);
  assert.match(screen, /SettingsNotifySwitch/);
  assert.match(screen, /language/);
  assert.match(screen, /settingsAppearance/);
  assert.match(screen, /SettingsAppearanceToggle/);
  assert.match(screen, /settingsHelpSupport/);
  assert.match(screen, /settingsAiLimits/);
  assert.match(screen, /SETTINGS_ICONS\.limits/);
  assert.match(screen, /onOpenAiLimits/);
  assert.match(screen, /settingsTermsPrivacy/);
  assert.match(screen, /dataDeletion/);
  assert.match(screen, /SettingsDeleteCard/);
  assert.match(screen, /SettingsLogoutButton/);
  assert.match(screen, /onLogout/);
  assert.match(screen, /SettingsFooter/);
  assert.match(screen, /APP_VERSION/);
  assert.match(screen, /APP_BUILD_LABEL/);
  assert.match(screen, /LEGAL_URLS\.supportMailto/);
  assert.match(screen, /LEGAL_URLS\.terms/);
  assert.match(screen, /LEGAL_URLS\.dataDeletion/);
  assert.match(screen, /onOpenNotifications/);
  assert.match(screen, /setLanguage/);
  assert.match(screen, /setMode/);
  assert.match(screen, /patchOwnerDisplayName/);
  assert.match(screen, /requestOwnerEmailChange/);
  assert.match(screen, /stackedTitle/);

  assert.doesNotMatch(screen, /settingsAboutLinas/);
  assert.doesNotMatch(screen, /SettingsAboutSheet/);
  assert.doesNotMatch(screen, /settingsBusinessProfile/);
  assert.doesNotMatch(screen, /linkApple/);
  assert.doesNotMatch(screen, /unlinkApple/);
  assert.doesNotMatch(en, /About Linas AI/);
  assert.doesNotMatch(ar, /حول Linas AI/);
  assert.doesNotMatch(fr, /À propos de Linas AI/);
  assert.equal(existsSync(join(root, 'src/features/settings/SettingsAboutSheet.tsx')), false);

  assert.match(tree, /section: 'ai_limits'/);
  assert.match(tree, /backTo: 'settings'/);
  assert.match(enAll, /settingsAiLimits: 'AI Limits'/);
  assert.match(arAll, /settingsAiLimits: 'حدود الذكاء الاصطناعي'/);
  assert.match(frAll, /settingsAiLimits: 'Limites IA'/);

  assert.match(chrome, /SettingsLogoutButton/);
  assert.match(chrome, /tr\('logout'\)/);
  assert.match(chrome, /settingsDeleteAccount/);
  assert.match(chrome, /settingsVersionFooter/);
  assert.match(chrome, /limits: feather\('sliders'\)/);
  assert.match(chrome, /colors\.accentGlow/);
  assert.match(shell, /stackedTitle/);
  assert.match(shell, /titleHairline/);
  assert.match(shell, /marginHorizontal:\s*spacing\.sm/);
  assert.match(shell, /colors\.drawerSurface/);
  assert.match(en, /Chats & request alerts/);
  assert.match(en, /Terms & Privacy/);
  assert.match(en, /Support & Legal/);
  assert.match(ar, /تنبيهات الدردشات والطلبات/);
  assert.match(fr, /Alertes chats et demandes/);
});

test('Settings still hosts Notifications and Logout; drawer does not', () => {
  const settings = read('features/settings/SettingsScreen.tsx');
  const nav = read('features/nav/NavDrawer.tsx');
  assert.match(settings, /onOpenNotifications/);
  assert.match(settings, /notificationsTitle/);
  assert.match(settings, /SettingsLogoutButton/);
  assert.doesNotMatch(nav, /onOpenNotifications/);
  assert.doesNotMatch(nav, /onLogout/);
});
