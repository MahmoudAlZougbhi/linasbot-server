import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { SideDrawer } from '../../components/SideDrawer';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import { CONTROL_ITEMS, type ControlArea, type ControlItem } from './controlAreas';

type Props = {
  open: boolean;
  onClose: () => void;
  onOpen: (area: ControlArea) => void;
  onLogout: () => void;
  isPlatformOwner: boolean;
};

const ORDER: ControlItem['group'][] = ['operate', 'grow', 'account', 'owner'];

const GROUP_I18N = {
  operate: 'groupOperate',
  grow: 'groupGrow',
  account: 'groupAccount',
  owner: 'groupOwner',
} as const;

export function ControlCenterDrawer({
  open,
  onClose,
  onOpen,
  onLogout,
  isPlatformOwner,
}: Props) {
  const { tr, isRtl } = useI18n();
  const items = CONTROL_ITEMS.filter((a) => !a.ownerOnly || isPlatformOwner);

  return (
    <SideDrawer open={open} side={isRtl ? 'left' : 'right'} onClose={onClose} widthRatio={0.86}>
      <Text style={styles.heading}>{tr('controlCenter')}</Text>
      <Text style={styles.sub}>Linas AI System Copilot</Text>
      <ScrollView contentContainerStyle={styles.list}>
        {ORDER.map((group) => {
          const rows = items.filter((i) => i.group === group);
          if (rows.length === 0) {
            return null;
          }
          return (
            <View key={group} style={styles.group}>
              <Text style={styles.groupLabel}>{tr(GROUP_I18N[group])}</Text>
              {rows.map((area) => (
                <Pressable key={area.id} style={styles.row} onPress={() => onOpen(area.id)}>
                  <Text style={styles.rowTitle}>{area.title}</Text>
                  <Text style={styles.rowSub}>{area.subtitle}</Text>
                </Pressable>
              ))}
            </View>
          );
        })}
        <Pressable style={styles.logout} onPress={onLogout}>
          <Text style={styles.logoutText}>{tr('logout')}</Text>
        </Pressable>
      </ScrollView>
    </SideDrawer>
  );
}

const styles = StyleSheet.create({
  heading: { color: colors.text, fontFamily: fonts.display, fontSize: 24 },
  sub: {
    color: colors.textMuted,
    fontFamily: fonts.body,
    fontSize: 13,
    marginBottom: spacing.lg,
    marginTop: 4,
  },
  list: { paddingBottom: 40, gap: 4 },
  group: { marginBottom: spacing.lg },
  groupLabel: {
    color: colors.textDim,
    fontFamily: fonts.bodyMedium,
    fontSize: 11,
    letterSpacing: 1,
    textTransform: 'uppercase',
    marginBottom: spacing.sm,
  },
  row: {
    backgroundColor: colors.bgElevated,
    borderRadius: radii.md,
    padding: spacing.lg - 2,
    borderColor: colors.border,
    borderWidth: 1,
    marginBottom: spacing.sm,
  },
  rowTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 16 },
  rowSub: { color: colors.textMuted, fontFamily: fonts.body, marginTop: 3, fontSize: 12 },
  logout: { marginTop: spacing.md, padding: spacing.lg, alignItems: 'center' },
  logoutText: { color: colors.danger, fontFamily: fonts.bodyMedium, fontWeight: '700' },
});
