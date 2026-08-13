import { Linking, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../theme';
import type { AppVersionCheck } from './appVersionApi';

type Props = {
  check: AppVersionCheck;
  onDismiss: () => void;
};

function storeUrl(check: AppVersionCheck): string | null {
  return Platform.OS === 'ios'
    ? check.ios_store_url ?? null
    : check.android_store_url ?? null;
}

/** Non-blocking banner when a newer marketing version is available. */
export function AppUpdateBanner({ check, onDismiss }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const insets = useSafeAreaInsets();
  const url = storeUrl(check);

  return (
    <View
      style={[
        styles.wrap,
        {
          paddingTop: Math.max(insets.top, spacing.sm),
          backgroundColor: colors.surfaceAlt,
          borderBottomColor: colors.border,
        },
      ]}
    >
      <View style={styles.copy}>
        <Text style={[styles.title, { color: colors.text }]}>{tr('appUpdateAvailableTitle')}</Text>
        <Text style={[styles.body, { color: colors.textMuted }]}>
          {tr('appUpdateAvailableBody').replace('{latest}', check.latest_version)}
        </Text>
      </View>
      <View style={styles.actions}>
        {url ? (
          <Pressable
            onPress={() => void Linking.openURL(url)}
            accessibilityRole="button"
            accessibilityLabel={tr('appUpdateOpenStore')}
          >
            <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>{tr('appUpdateOpenStore')}</Text>
          </Pressable>
        ) : null}
        <Pressable onPress={onDismiss} accessibilityRole="button" accessibilityLabel={tr('appUpdateDismiss')}>
          <Text style={{ color: colors.textDim, fontFamily: fonts.body }}>{tr('appUpdateDismiss')}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
    gap: spacing.sm,
  },
  copy: { gap: 4 },
  title: { fontFamily: fonts.bodyMedium, fontSize: 14 },
  body: { fontFamily: fonts.body, fontSize: 12 },
  actions: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg },
});
