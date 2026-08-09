import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { APP_ENV, APP_VERSION, IOS_BUILD, LEGAL_URLS } from '../../config';
import { colors } from '../../theme/colors';

type Props = {
  onBack: () => void;
  onLogout: () => void;
};

async function open(url: string) {
  await Linking.openURL(url);
}

export function SettingsScreen({ onBack, onLogout }: Props) {
  return (
    <View style={styles.root}>
      <Pressable onPress={onBack}>
        <Text style={styles.link}>Back</Text>
      </Pressable>
      <Text style={styles.title}>Settings</Text>
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

      <Pressable style={styles.logout} onPress={onLogout}>
        <Text style={styles.logoutText}>Log out</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg, paddingTop: 56, paddingHorizontal: 16 },
  link: { color: colors.accent, marginBottom: 8 },
  title: { color: colors.text, fontSize: 28, fontWeight: '700', marginBottom: 8 },
  meta: { color: colors.textMuted, marginBottom: 20 },
  row: {
    backgroundColor: colors.surface,
    borderRadius: 14,
    padding: 16,
    borderColor: colors.border,
    borderWidth: 1,
    marginBottom: 10,
  },
  rowTitle: { color: colors.text, fontWeight: '700', fontSize: 16 },
  logout: { marginTop: 28, alignItems: 'center', padding: 16 },
  logoutText: { color: colors.danger, fontWeight: '700' },
});
