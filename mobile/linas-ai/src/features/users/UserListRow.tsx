import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import type { StringKey } from '../../i18n/locales/en';
import { colors, fonts, radii } from '../../theme';
import { accessSummaryKeys, displayPermissions } from './usersAccess';
import { UserAvatar } from './UserAvatar';
import type { TeamUser } from './usersApi';
import type { TenantRole } from './usersRolesApi';

type Props = {
  user: TeamUser;
  roles: TenantRole[];
  last: boolean;
  disabled?: boolean;
  onMenu: () => void;
};

const ROLE_LABEL: Record<string, StringKey> = {
  admin: 'roleAdmin',
  operator: 'roleOperator',
  viewer: 'roleViewer',
  platform_owner: 'rolePlatformOwner',
};

function roleLabel(user: TeamUser, roles: TenantRole[], tr: (key: StringKey) => string): string {
  const custom = roles.find((role) => role.id === user.role && !role.system);
  if (custom) return custom.name;
  const key = ROLE_LABEL[user.role];
  return key ? tr(key) : user.role;
}

export function UserListRow({ user, roles, last, disabled, onMenu }: Props) {
  const { tr } = useI18n();
  const name = user.name || user.displayName || user.email;
  const blocked = user.status === 'suspended' || user.status === 'inactive';
  const catalog = roles.find((role) => role.id === user.role);
  const perms = displayPermissions(user.role, user.permissions, catalog?.permissions);
  const summaryKeys = accessSummaryKeys(perms);
  const summary =
    summaryKeys[0] === 'usersFullAccess'
      ? tr('usersFullAccess')
      : summaryKeys.map((key) => tr(key)).join(' · ') || tr('usersNoAccess');

  return (
    <View style={[styles.row, !last && styles.divider]}>
      <UserAvatar name={name} email={user.email} />
      <View style={styles.meta}>
        <View style={styles.topLine}>
          <Text style={styles.name} numberOfLines={1}>
            {name}
          </Text>
          {blocked ? (
            <View style={styles.blocked}>
              <View style={styles.blockedDot} />
              <Text style={styles.blockedText}>{tr('usersBlocked')}</Text>
            </View>
          ) : (
            <View style={styles.active}>
              <View style={styles.activeDot} />
              <Text style={styles.activeText}>{tr('statusActive')}</Text>
            </View>
          )}
        </View>
        <Text style={styles.email} numberOfLines={1}>
          {user.email}
        </Text>
        <View style={styles.bottom}>
          <View style={styles.pill}>
            <Text style={styles.pillText}>{roleLabel(user, roles, tr)}</Text>
          </View>
          <Text style={styles.summary} numberOfLines={2}>
            {summary}
          </Text>
        </View>
      </View>
      <Pressable
        onPress={onMenu}
        disabled={disabled}
        hitSlop={8}
        accessibilityRole="button"
        accessibilityLabel={tr('usersEdit')}
        style={({ pressed }) => [styles.menu, pressed && styles.pressed]}
      >
        <AppIcon icon={feather('more-horizontal')} size={20} color={colors.textMuted} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: 14,
    paddingHorizontal: 14,
    gap: 12,
  },
  divider: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.borderSoft,
  },
  meta: { flex: 1, minWidth: 0, gap: 3 },
  topLine: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  name: { flex: 1, fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700', color: colors.text },
  email: { fontFamily: fonts.body, fontSize: 13, color: colors.textMuted },
  bottom: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4, flexWrap: 'wrap' },
  pill: {
    backgroundColor: colors.accentSoft,
    borderRadius: radii.sm,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  pillText: { color: colors.accentDeep, fontFamily: fonts.bodyMedium, fontSize: 12 },
  summary: { flex: 1, fontFamily: fonts.body, fontSize: 12, color: colors.textDim },
  active: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  activeDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#22C55E' },
  activeText: { fontFamily: fonts.body, fontSize: 12, color: colors.textMuted },
  blocked: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    backgroundColor: '#FEE2E2',
    borderRadius: radii.pill,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  blockedDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#9CA3AF' },
  blockedText: { fontFamily: fonts.bodyMedium, fontSize: 12, color: '#B91C1C' },
  menu: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center', marginTop: 2 },
  pressed: { opacity: 0.55 },
});
