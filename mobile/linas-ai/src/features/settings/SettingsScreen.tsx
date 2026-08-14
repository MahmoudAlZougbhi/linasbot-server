import { useCallback, useEffect, useState } from 'react';
import { Alert, Linking, ScrollView, StyleSheet } from 'react-native';

import { APP_BUILD_LABEL, APP_VERSION, LEGAL_URLS } from '../../config';
import { tokenStore } from '../../auth/tokenStore';
import { useI18n } from '../../i18n/LanguageContext';
import type { AppLanguage } from '../../i18n';
import { spacing, useTheme } from '../../theme';
import { deleteAccount } from '../auth/appleAccount';
import { useModuleNav } from '../nav/ModuleNavContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import {
  SETTINGS_ICONS,
  SettingsAppearanceToggle,
  SettingsDeleteCard,
  SettingsFooter,
  SettingsLogoutButton,
  SettingsNotifySwitch,
  SettingsRow,
  SettingsSection,
} from './SettingsChrome';
import { SettingsEmailSheet, SettingsLanguageSheet, SettingsNameSheet } from './SettingsEditors';
import {
  fetchOwnerSettingsProfile,
  patchOwnerDisplayName,
  requestOwnerEmailChange,
  settingsApiErrorMessage,
} from './settingsProfileApi';

type Props = {
  onLogout: () => void;
  onOpenNotifications?: () => void;
  onOpenAiLimits?: () => void;
};

type Sheet = 'none' | 'name' | 'email' | 'language';

async function open(url: string) {
  await Linking.openURL(url);
}

function languageLabel(lang: AppLanguage, tr: (key: 'settingsLangEn' | 'settingsLangAr' | 'settingsLangFr') => string) {
  if (lang === 'ar') return tr('settingsLangAr');
  if (lang === 'fr') return tr('settingsLangFr');
  return tr('settingsLangEn');
}

/** iOS Settings handoff — ACCOUNT / PREFERENCES / SUPPORT & LEGAL cards. */
export function SettingsScreen({
  onLogout,
  onOpenNotifications,
  onOpenAiLimits,
}: Props) {
  const { tr, language, setLanguage } = useI18n();
  const { resolved, setMode } = useTheme();
  const nav = useModuleNav();
  const [sheet, setSheet] = useState<Sheet>('none');
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [nameBusy, setNameBusy] = useState(false);
  const [emailBusy, setEmailBusy] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [emailNotice, setEmailNotice] = useState<string | null>(null);

  const loadProfile = useCallback(async () => {
    const stored = await tokenStore.getUser();
    if (stored) {
      setDisplayName(stored.displayName || stored.name || '');
      setEmail(stored.email);
    }
    try {
      const profile = await fetchOwnerSettingsProfile();
      setDisplayName(profile.displayName);
      if (profile.email) setEmail(profile.email);
    } catch {
      /* signed-in cache already applied; guest / 401 leaves fields empty */
    }
  }, []);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile, nav.areaFocusNonce]);

  function confirmDeleteAccount() {
    if (deleteBusy) return;
    Alert.alert(tr('settingsDeleteAccountTitle'), tr('settingsDeleteAccountConfirm'), [
      { text: tr('settingsAppleCancel'), style: 'cancel' },
      {
        text: tr('settingsDeleteAccountAction'),
        style: 'destructive',
        onPress: () => void runDeleteAccount(),
      },
    ]);
  }

  async function runDeleteAccount() {
    if (deleteBusy) return;
    setDeleteBusy(true);
    try {
      const result = await deleteAccount();
      if (result.ok) {
        onLogout();
        return;
      }
      Alert.alert(tr('settingsDeleteAccount'), tr('settingsAppleDeleteError'));
    } finally {
      setDeleteBusy(false);
    }
  }

  async function saveName(next: string) {
    const cleaned = next.trim();
    if (!cleaned) {
      setNameError(tr('settingsNameRequired'));
      return;
    }
    setNameBusy(true);
    setNameError(null);
    try {
      const profile = await patchOwnerDisplayName(cleaned);
      setDisplayName(profile.displayName);
      setSheet('none');
    } catch (err) {
      setNameError(settingsApiErrorMessage(err, tr('settingsNameSaveError')));
    } finally {
      setNameBusy(false);
    }
  }

  async function saveEmail(nextEmail: string, password: string) {
    setEmailBusy(true);
    setEmailError(null);
    setEmailNotice(null);
    try {
      const message = await requestOwnerEmailChange(nextEmail, password);
      setEmailNotice(message || tr('settingsEmailChangeSent'));
    } catch (err) {
      setEmailError(settingsApiErrorMessage(err, tr('settingsEmailSaveError')));
    } finally {
      setEmailBusy(false);
    }
  }

  function openNotifications() {
    onOpenNotifications?.();
  }

  return (
    <ScreenChrome title={tr('settings')}>
      <ScrollView
        contentContainerStyle={styles.list}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        <SettingsSection title={tr('groupAccount')}>
          <SettingsRow
            icon={SETTINGS_ICONS.name}
            label={tr('settingsChangeName')}
            value={displayName}
            onPress={() => {
              setNameError(null);
              setSheet('name');
            }}
          />
          <SettingsRow
            icon={SETTINGS_ICONS.email}
            label={tr('changeEmail')}
            value={email}
            onPress={() => {
              setEmailError(null);
              setEmailNotice(null);
              setSheet('email');
            }}
          />
          <SettingsRow
            icon={SETTINGS_ICONS.bell}
            label={tr('notificationsTitle')}
            hint={tr('settingsNotificationsHint')}
            showChevron={false}
            last
            onPress={onOpenNotifications ? openNotifications : undefined}
            accessory={
              onOpenNotifications ? (
                <SettingsNotifySwitch value onValueChange={() => openNotifications()} />
              ) : null
            }
          />
        </SettingsSection>

        <SettingsSection title={tr('settingsPreferences')}>
          <SettingsRow
            icon={SETTINGS_ICONS.globe}
            label={tr('language')}
            value={languageLabel(language, tr)}
            onPress={() => setSheet('language')}
          />
          <SettingsRow
            icon={SETTINGS_ICONS.appearance}
            label={tr('settingsAppearance')}
            showChevron={false}
            last
            accessory={<SettingsAppearanceToggle resolved={resolved} onSelect={setMode} />}
          />
        </SettingsSection>

        <SettingsSection title={tr('settingsSupportLegal')}>
          <SettingsRow
            icon={SETTINGS_ICONS.help}
            label={tr('settingsHelpSupport')}
            onPress={() => void open(LEGAL_URLS.supportMailto)}
          />
          <SettingsRow
            icon={SETTINGS_ICONS.limits}
            label={tr('settingsAiLimits')}
            onPress={onOpenAiLimits}
          />
          <SettingsRow
            icon={SETTINGS_ICONS.terms}
            label={tr('settingsTermsPrivacy')}
            onPress={() => void open(LEGAL_URLS.terms)}
          />
          <SettingsRow
            icon={SETTINGS_ICONS.data}
            label={tr('dataDeletion')}
            last
            onPress={() => void open(LEGAL_URLS.dataDeletion)}
          />
        </SettingsSection>

        <SettingsDeleteCard onPress={confirmDeleteAccount} />
        <SettingsLogoutButton onPress={onLogout} />
        <SettingsFooter version={APP_VERSION} build={APP_BUILD_LABEL} />
      </ScrollView>

      <SettingsNameSheet
        visible={sheet === 'name'}
        initialName={displayName}
        busy={nameBusy}
        error={nameError}
        onClose={() => setSheet('none')}
        onSave={(name) => void saveName(name)}
      />
      <SettingsEmailSheet
        visible={sheet === 'email'}
        busy={emailBusy}
        error={emailError}
        notice={emailNotice}
        onClose={() => setSheet('none')}
        onSave={(next, password) => void saveEmail(next, password)}
      />
      <SettingsLanguageSheet
        visible={sheet === 'language'}
        language={language}
        onClose={() => setSheet('none')}
        onSelect={setLanguage}
      />
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: spacing.lg, paddingTop: spacing.sm },
});
