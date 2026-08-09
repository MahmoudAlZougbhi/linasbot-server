import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { APP_ENV, APP_VERSION, IOS_BUILD, LEGAL_URLS } from '../../config';
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
  return (
    <ScreenChrome title="Settings" subtitle="Legal & app info" onBack={onBack}>
      <Text style={styles.meta}>
        Linas AI {APP_VERSION} ({APP_ENV}) · iOS build {IOS_BUILD}
      </Text>
      <Pressable style={styles.row} onPress={() => void open(LEGAL_URLS.privacy)}>
        <Text style={styles.rowTitle}>Privacy Policy</Text>
      </Pressable>
      <Pressable style={styles.row} onPress={() => void open(LEGAL_URLS.terms)}>
        <Text style={styles.rowTitle}>Terms</Text>
      </Pressable>
      <Pressable style={styles.row} onPress={() => void open(LEGAL_URLS.dataDeletion)}>
        <Text style={styles.rowTitle}>Data Deletion</Text>
      </Pressable>
      <View style={styles.logout}>
        <PrimaryButton label="Log out" variant="danger" onPress={onLogout} />
      </View>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  meta: { color: colors.textMuted, fontFamily: fonts.body, marginBottom: spacing.lg },
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
