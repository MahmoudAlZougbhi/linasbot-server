/**
 * Settings iOS handoff — sections, copy, logout, version, existing destinations.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
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
  const en = read('i18n/locales/settingsUiEn.ts');
  const ar = read('i18n/locales/settingsUiAr.ts');
  const fr = read('i18n/locales/settingsUiFr.ts');

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
  assert.match(screen, /onOpenAiLimits/);
  assert.doesNotMatch(screen, /settingsAboutLinas/);
  assert.doesNotMatch(screen, /SettingsAboutSheet/);
  assert.doesNotMatch(screen, /settingsBusinessProfile/);
  assert.doesNotMatch(screen, /linkApple/);
  assert.doesNotMatch(screen, /unlinkApple/);
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

  assert.match(chrome, /SettingsLogoutButton/);
  assert.match(chrome, /tr\('logout'\)/);
  assert.match(chrome, /settingsDeleteAccount/);
  assert.match(chrome, /settingsVersionFooter/);
  assert.match(en, /Chats & request alerts/);
  assert.doesNotMatch(en, /About Linas AI/);
  assert.match(en, /Terms & Privacy/);
  assert.match(en, /Support & Legal/);
  assert.match(read('i18n/locales/en.ts'), /settingsAiLimits: 'AI Limits'/);
  assert.match(ar, /تنبيهات الدردشات والطلبات/);
  assert.match(fr, /Alertes chats et demandes/);
});

test('Settings visual handoff: stacked title, inset hairline, pale canvas, light icon wash', () => {
  const screen = read('features/settings/SettingsScreen.tsx');
  const chrome = read('features/settings/SettingsChrome.tsx');
  const shared = read('features/shared/ScreenChrome.tsx');
  const live = read('features/livechat/LiveChatScreen.tsx');

  assert.match(screen, /stackedHeader/);
  assert.match(screen, /canvasColor=\{SETTINGS_CANVAS\[resolved\]\}/);
  assert.match(screen, /settingsAiLimits/);
  assert.doesNotMatch(screen, /settingsAboutLinas|SettingsAboutSheet|linkApple|unlinkApple/);

  assert.match(chrome, /SETTINGS_ICON_WASH/);
  assert.match(chrome, /rgba\(0, 139, 139, 0\.08\)/);
  assert.match(chrome, /SETTINGS_CANVAS/);
  assert.match(chrome, /#F2F4F4/);
  assert.doesNotMatch(chrome, /iconBg = danger \? .*: colors\.accentSoft/);

  assert.match(shared, /stackedHeader/);
  assert.match(shared, /styles\.menuRow/);
  assert.match(shared, /styles\.stackedTitle/);
  assert.match(shared, /styles\.titleRule/);
  assert.match(shared, /marginHorizontal: spacing\.lg/);
  assert.match(shared, /height: StyleSheet\.hairlineWidth/);
  assert.doesNotMatch(live, /stackedHeader/);

  assert.match(chrome, /sectionTitle:\s*\{[^}]*fontFamily:\s*fonts\.body,/);
  assert.match(chrome, /sectionTitle:\s*\{[^}]*fontSize:\s*11/);
  assert.match(chrome, /sectionTitle:\s*\{[^}]*letterSpacing:\s*1\.2/);
  assert.match(chrome, /sectionTitle:\s*\{[^}]*textTransform:\s*'uppercase'/);
  assert.doesNotMatch(chrome, /sectionTitle:\s*\{[^}]*fontSize:\s*(1[2-9]|2\d)/);
  assert.match(chrome, /styles\.sectionTitle[^\n]*maxFontSizeMultiplier=\{1\.2\}/);
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
