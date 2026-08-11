import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { APP_BUILD_LABEL, APP_VERSION, LEGAL_URLS } from '../../config';
import { useI18n } from '../../i18n/LanguageContext';
import type { AppLanguage } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { useModuleNav } from '../nav/ModuleNavContext';
import { ScreenChrome } from '../shared/ScreenChrome';

type Props = {
  onLogout: () => void;
  onOpenNotifications?: () => void;
  onOpenActions?: () => void;
  onOpenAiLimits?: () => void;
};

async function open(url: string) {
  await Linking.openURL(url);
}

/** Grouped Settings; Actions / AI Limits hosted here (not in CM hub). */
export function SettingsScreen({
  onLogout,
  onOpenNotifications,
  onOpenActions,
  onOpenAiLimits,
}: Props) {
  const { tr, language, setLanguage } = useI18n();
  const { colors, mode, setMode } = useTheme();
  const nav = useModuleNav();

  return (
    <ScreenChrome title={tr('settings')} subtitle={tr('settingsSub')}>
      <Text style={[styles.meta, { color: colors.textMuted }]}>
        Linas AI {APP_VERSION} · build {APP_BUILD_LABEL}
      </Text>

      <Text style={[styles.group, { color: colors.textDim }]}>{tr('groupAccount')}</Text>
      <Row
        title={tr('settingsSignedInProfile')}
        subtitle={tr('settingsSignedInProfileSub')}
        onPress={() => undefined}
        disabled
      />
      <Row
        title={tr('settingsBusinessProfile')}
        subtitle={tr('settingsBusinessProfileSub')}
        onPress={nav.goChat}
        note={tr('settingsBusinessProfileNote')}
      />
      {onOpenNotifications ? (
        <Row
          title={tr('notificationsTitle')}
          subtitle={tr('notificationsSub')}
          onPress={onOpenNotifications}
        />
      ) : null}

      <Text style={[styles.group, { color: colors.textDim }]}>{tr('settingsPreferences')}</Text>
      <Text style={[styles.label, { color: colors.textMuted }]}>{tr('language')}</Text>
      <View style={styles.chips}>
        {(['en', 'ar', 'fr'] as AppLanguage[]).map((lang) => (
          <Pressable
            key={lang}
            style={[
              styles.chip,
              { borderColor: colors.border, backgroundColor: colors.bgElevated },
              language === lang && { borderColor: colors.accent, backgroundColor: colors.surfaceAlt },
            ]}
            onPress={() => setLanguage(lang)}
            accessibilityLabel={`${tr('language')} ${lang}`}
          >
            <Text style={{ color: colors.text, fontFamily: fonts.bodyMedium }}>{lang.toUpperCase()}</Text>
          </Pressable>
        ))}
      </View>
      <Text style={[styles.label, { color: colors.textMuted }]}>{tr('settingsAppearance')}</Text>
      <View style={styles.chips}>
        {(['system', 'light', 'dark'] as const).map((m) => (
          <Pressable
            key={m}
            style={[
              styles.chip,
              { borderColor: colors.border, backgroundColor: colors.bgElevated },
              mode === m && { borderColor: colors.accent, backgroundColor: colors.surfaceAlt },
            ]}
            onPress={() => setMode(m)}
            accessibilityLabel={`${tr('settingsAppearance')} ${m}`}
          >
            <Text style={{ color: colors.text, fontFamily: fonts.bodyMedium }}>{m}</Text>
          </Pressable>
        ))}
      </View>

      {onOpenActions || onOpenAiLimits ? (
        <>
          <Text style={[styles.group, { color: colors.textDim }]}>{tr('settingsAiSection')}</Text>
          {onOpenActions ? (
            <Row
              title={tr('settingsActions')}
              subtitle={tr('settingsActionsSub')}
              onPress={onOpenActions}
            />
          ) : null}
          {onOpenAiLimits ? (
            <Row
              title={tr('settingsAiLimits')}
              subtitle={tr('settingsAiLimitsSub')}
              onPress={onOpenAiLimits}
            />
          ) : null}
        </>
      ) : null}

      <Text style={[styles.group, { color: colors.textDim }]}>{tr('settingsSecuritySupport')}</Text>
      <Row title={tr('settingsPrivacyData')} onPress={() => void open(LEGAL_URLS.privacy)} />
      <Row
        title={tr('settingsHelpSupport')}
        onPress={() => void open(LEGAL_URLS.terms)}
        note={tr('settingsHelpSupportNote')}
      />
      <Row title={tr('settingsAboutLegal')} onPress={() => void open(LEGAL_URLS.terms)} />
      <Row title={tr('terms')} onPress={() => void open(LEGAL_URLS.terms)} />
      <Row title={tr('privacy')} onPress={() => void open(LEGAL_URLS.privacy)} />
      <Row title={tr('dataDeletion')} onPress={() => void open(LEGAL_URLS.dataDeletion)} />

      <View style={styles.logout}>
        <PrimaryButton label={tr('logout')} variant="danger" onPress={onLogout} />
      </View>
    </ScreenChrome>
  );
}

function Row({
  title,
  subtitle,
  note,
  onPress,
  disabled,
}: {
  title: string;
  subtitle?: string;
  note?: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      style={[
        styles.row,
        { backgroundColor: colors.surface, borderColor: colors.border, opacity: disabled ? 0.55 : 1 },
      ]}
      onPress={onPress}
      disabled={disabled}
      accessibilityLabel={title}
    >
      <Text style={{ color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 16 }}>{title}</Text>
      {subtitle ? (
        <Text style={{ color: colors.textMuted, marginTop: 4, fontSize: 12 }}>{subtitle}</Text>
      ) : null}
      {note ? <Text style={{ color: colors.textDim, marginTop: 4, fontSize: 11 }}>{note}</Text> : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  meta: { fontFamily: fonts.body, marginBottom: spacing.lg },
  group: {
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
  },
  label: { fontFamily: fonts.body, fontSize: 12, marginBottom: spacing.sm },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: spacing.md },
  chip: {
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 10,
    minHeight: 44,
    justifyContent: 'center',
  },
  row: {
    borderRadius: radii.md,
    padding: spacing.lg,
    borderWidth: 1,
    marginBottom: spacing.sm,
    minHeight: 48,
    justifyContent: 'center',
  },
  logout: { marginTop: spacing.xxl, marginBottom: spacing.xxl },
});
