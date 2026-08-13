import { Linking, Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import { GradientBackground } from '../../components/GradientBackground';
import { LinasStarMark } from '../../components/LinasStarMark';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import type { AppVersionCheck } from './appVersionApi';

type Props = {
  check: AppVersionCheck;
};

function storeUrl(check: AppVersionCheck): string | null {
  return Platform.OS === 'ios'
    ? check.ios_store_url ?? null
    : check.android_store_url ?? null;
}

/** Blocks app use when installed marketing version is below server minimum. */
export function AppUpdateGateScreen({ check }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const url = storeUrl(check);

  return (
    <GradientBackground>
      <View style={styles.wrap}>
        <LinasStarMark size={48} />
        <Text style={[styles.title, { color: colors.text }]}>{tr('appUpdateForceTitle')}</Text>
        <Text style={[styles.body, { color: colors.textMuted }]}>
          {tr('appUpdateForceBody')
            .replace('{min}', check.min_supported_version)
            .replace('{latest}', check.latest_version)}
        </Text>
        {url ? (
          <Pressable
            style={[styles.btn, { backgroundColor: colors.accent }]}
            onPress={() => void Linking.openURL(url)}
            accessibilityRole="button"
            accessibilityLabel={tr('appUpdateOpenStore')}
          >
            <Text style={styles.btnText}>{tr('appUpdateOpenStore')}</Text>
          </Pressable>
        ) : null}
      </View>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    gap: spacing.md,
  },
  title: { fontFamily: fonts.display, fontSize: 24, textAlign: 'center', marginTop: spacing.md },
  body: { fontFamily: fonts.body, fontSize: 14, textAlign: 'center', maxWidth: 340 },
  btn: {
    marginTop: spacing.md,
    minHeight: 48,
    borderRadius: radii.md,
    paddingHorizontal: 28,
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'stretch',
  },
  btnText: { color: '#fff', fontFamily: fonts.bodyMedium, fontSize: 16 },
});
