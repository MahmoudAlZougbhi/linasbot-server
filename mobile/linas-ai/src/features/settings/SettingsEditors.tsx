import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { TextField } from '../../components/TextField';
import { AuthPasswordField } from '../auth/AuthFields';
import { useI18n } from '../../i18n/LanguageContext';
import type { AppLanguage } from '../../i18n';
import { fonts, spacing, typography, useTheme } from '../../theme';
import { SettingsSheet } from './SettingsChrome';

export function SettingsNameSheet({
  visible,
  initialName,
  busy,
  error,
  onClose,
  onSave,
}: {
  visible: boolean;
  initialName: string;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onSave: (name: string) => void;
}) {
  const { tr } = useI18n();
  const { colors } = useTheme();
  const [name, setName] = useState(initialName);

  useEffect(() => {
    if (visible) setName(initialName);
  }, [visible, initialName]);

  return (
    <SettingsSheet visible={visible} title={tr('settingsChangeName')} onClose={onClose}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <TextField
          value={name}
          onChangeText={setName}
          placeholder={tr('settingsNamePlaceholder')}
          autoCapitalize="words"
          autoCorrect={false}
          editable={!busy}
        />
        {error ? <Text style={[styles.error, { color: colors.danger }]}>{error}</Text> : null}
        <PrimaryButton
          label={tr('settingsSave')}
          onPress={() => onSave(name)}
          loading={busy}
          disabled={busy}
        />
      </KeyboardAvoidingView>
    </SettingsSheet>
  );
}

export function SettingsEmailSheet({
  visible,
  busy,
  error,
  notice,
  onClose,
  onSave,
}: {
  visible: boolean;
  busy: boolean;
  error: string | null;
  notice: string | null;
  onClose: () => void;
  onSave: (email: string, password: string) => void;
}) {
  const { tr } = useI18n();
  const { colors } = useTheme();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  useEffect(() => {
    if (visible) {
      setEmail('');
      setPassword('');
    }
  }, [visible]);

  return (
    <SettingsSheet visible={visible} title={tr('changeEmail')} onClose={onClose}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <TextField
          value={email}
          onChangeText={setEmail}
          placeholder={tr('settingsNewEmail')}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="email-address"
          editable={!busy}
        />
        <AuthPasswordField
          value={password}
          onChangeText={setPassword}
          placeholder={tr('settingsCurrentPassword')}
          editable={!busy}
        />
        {error ? <Text style={[styles.error, { color: colors.danger }]}>{error}</Text> : null}
        {notice ? <Text style={[styles.notice, { color: colors.textMuted }]}>{notice}</Text> : null}
        <PrimaryButton
          label={tr('settingsSave')}
          onPress={() => onSave(email, password)}
          loading={busy}
          disabled={busy}
        />
      </KeyboardAvoidingView>
    </SettingsSheet>
  );
}

const LANGS: { id: AppLanguage; key: 'settingsLangEn' | 'settingsLangAr' | 'settingsLangFr' }[] = [
  { id: 'en', key: 'settingsLangEn' },
  { id: 'ar', key: 'settingsLangAr' },
  { id: 'fr', key: 'settingsLangFr' },
];

export function SettingsLanguageSheet({
  visible,
  language,
  onClose,
  onSelect,
}: {
  visible: boolean;
  language: AppLanguage;
  onClose: () => void;
  onSelect: (lang: AppLanguage) => void;
}) {
  const { tr } = useI18n();
  const { colors } = useTheme();
  return (
    <SettingsSheet visible={visible} title={tr('language')} onClose={onClose}>
      {LANGS.map((item) => {
        const selected = language === item.id;
        return (
          <Pressable
            key={item.id}
            onPress={() => {
              onSelect(item.id);
              onClose();
            }}
            accessibilityRole="button"
            accessibilityState={{ selected }}
            style={[styles.langRow, { borderColor: colors.border }]}
          >
            <Text style={[styles.langLabel, { color: colors.text }]}>{tr(item.key)}</Text>
            {selected ? <Text style={[styles.langCheck, { color: colors.accent }]}>✓</Text> : null}
          </Pressable>
        );
      })}
    </SettingsSheet>
  );
}

const styles = StyleSheet.create({
  error: { fontFamily: fonts.body, fontSize: 14, marginBottom: spacing.sm },
  notice: { fontFamily: fonts.body, fontSize: 14, marginBottom: spacing.sm },
  langRow: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 48,
    borderBottomWidth: StyleSheet.hairlineWidth,
    paddingVertical: 12,
  },
  langLabel: { flex: 1, ...typography.sectionTitle },
  langCheck: { fontFamily: fonts.bodyMedium, fontSize: 18, fontWeight: '700' },
});
