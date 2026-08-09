import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { colors } from '../../theme/colors';

type Props = {
  onBack: () => void;
  onOpen: (area: ControlArea) => void;
  onLogout: () => void;
  isPlatformOwner: boolean;
};

export type ControlArea =
  | 'cm'
  | 'create'
  | 'integrations'
  | 'usage'
  | 'subscription'
  | 'users'
  | 'scheduled'
  | 'settings'
  | 'owner';

const AREAS: { id: ControlArea; title: string; subtitle: string; ownerOnly?: boolean }[] = [
  { id: 'create', title: 'Create', subtitle: 'Creative Studio' },
  { id: 'cm', title: 'Content Management', subtitle: 'Manual AI configuration' },
  { id: 'integrations', title: 'Integrations', subtitle: 'Facebook / Instagram' },
  { id: 'usage', title: 'Usage & Credits', subtitle: 'Included usage and packs' },
  { id: 'subscription', title: 'Subscription', subtitle: 'Plan and renewal' },
  { id: 'users', title: 'Users', subtitle: 'Members and permissions' },
  { id: 'scheduled', title: 'Scheduled', subtitle: 'Upcoming posts' },
  { id: 'settings', title: 'Settings', subtitle: 'Account and security' },
  { id: 'owner', title: 'Owner Control Center', subtitle: 'Platform metrics', ownerOnly: true },
];

export function ControlCenterScreen({ onBack, onOpen, onLogout, isPlatformOwner }: Props) {
  return (
    <View style={styles.root}>
      <View style={styles.top}>
        <Pressable onPress={onBack}>
          <Text style={styles.link}>Back to chat</Text>
        </Pressable>
        <Text style={styles.title}>Control Center</Text>
      </View>
      <ScrollView contentContainerStyle={styles.list}>
        {AREAS.filter((a) => !a.ownerOnly || isPlatformOwner).map((area) => (
          <Pressable key={area.id} style={styles.row} onPress={() => onOpen(area.id)}>
            <Text style={styles.rowTitle}>{area.title}</Text>
            <Text style={styles.rowSub}>{area.subtitle}</Text>
          </Pressable>
        ))}
        <Pressable style={styles.logout} onPress={onLogout}>
          <Text style={styles.logoutText}>Log out</Text>
        </Pressable>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  top: { paddingTop: 56, paddingHorizontal: 16, paddingBottom: 12 },
  link: { color: colors.accent, marginBottom: 8 },
  title: { color: colors.text, fontSize: 28, fontWeight: '700' },
  list: { padding: 16, gap: 10 },
  row: {
    backgroundColor: colors.surface,
    borderRadius: 14,
    padding: 16,
    borderColor: colors.border,
    borderWidth: 1,
  },
  rowTitle: { color: colors.text, fontSize: 17, fontWeight: '700' },
  rowSub: { color: colors.textMuted, marginTop: 4 },
  logout: { marginTop: 24, padding: 16, alignItems: 'center' },
  logoutText: { color: colors.danger, fontWeight: '700' },
});
