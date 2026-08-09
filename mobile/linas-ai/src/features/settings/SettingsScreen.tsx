import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { APP_ENV, APP_VERSION, IOS_BUILD, LEGAL_URLS } from '../../config';
import { useI18n } from '../../i18n/LanguageContext';
import type { AppLanguage } from '../../i18n';
import { colors, fonts, radii, spacing } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';

type Props = {
  onBack: () => void;
  onLogout: () => void;
};

async function open(url: string) {
  await Linking.openURL(url);
}

export function SettingsScreen({ onBack, onLogout }: Props) {
  const { tr, language, setLanguage } = useI18n();

  return (
    <ScreenChrome title={tr('settings')} subtitle={tr('settingsSub')} onBack={onBack}>
      <Text style={styles.meta}>
        Linas AI {APP_VERSION} ({APP_ENV}) · iOS build {IOS_BUILD}
      </Text>

      <Text style={styles.section}>{tr('language')}</Text>
      <View style={styles.chips}>
        {(['en', 'ar', 'fr'] as AppLanguage[]).map((lang) => (
          <Pressable
            key={lang}
            style={[styles.chip, language === lang && styles.chipOn]}
            onPress={() => setLanguage(lang)}
          >
            <Text style={styles.chipText}>{lang.toUpperCase()}</Text>
          </Pressable>
        ))}
      </View>

      <Pressable style={styles.row} onPress={() => void open(LEGAL_URLS.privacy)}>
        <Text style={styles.rowTitle}>{tr('privacy')}</Text>
      </Pressable>
      <Pressable style={styles.row} onPress={() => void open(LEGAL_URLS.terms)}>
        <Text style={styles.rowTitle}>{tr('terms')}</Text>
      </Pressable>
      <Pressable style={styles.row} onPress={() => void open(LEGAL_URLS.dataDeletion)}>
        <Text style={styles.rowTitle}>{tr('dataDeletion')}</Text>
      </Pressable>
      <View style={styles.logout}>
        <PrimaryButton label={tr('logout')} variant="danger" onPress={onLogout} />
      </View>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  meta: { color: colors.textMuted, fontFamily: fonts.body, marginBottom: spacing.lg },
  section: {
    color: colors.textDim,
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
    marginBottom: spacing.sm,
  },
  chips: { flexDirection: 'row', gap: 8, marginBottom: spacing.lg },
  chip: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 8,
    backgroundColor: colors.bgElevated,
  },
  chipOn: { borderColor: colors.accent, backgroundColor: colors.surfaceAlt },
  chipText: { color: colors.text, fontFamily: fonts.bodyMedium },
  row: {
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    padding: spacing.lg,
    borderColor: colors.border,
    borderWidth: 1,
    marginBottom: spacing.sm,
  },
  rowTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 16 },
  logout: { marginTop: spacing.xxl },
});
