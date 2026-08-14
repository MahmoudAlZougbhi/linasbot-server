import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppIcon, feather, ion, mci } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import type { StringKey } from '../../i18n/locales/en';
import { colors, fonts, radii, spacing } from '../../theme';
import { UserAvatar } from './UserAvatar';
import type { TeamUser } from './usersApi';
import type { TenantRole } from './usersRolesApi';

type Props = {
  user: TeamUser;
  roles: TenantRole[];
  busy?: boolean;
  onEdit: () => void;
  onResetPassword: () => void;
  onToggleBlock: () => void;
  onDelete: () => void;
  onClose: () => void;
};

const ROLE_LABEL: Record<string, StringKey> = {
  admin: 'roleAdmin',
  operator: 'roleOperator',
  viewer: 'roleViewer',
  platform_owner: 'rolePlatformOwner',
};

export function UserActionSheet({
  user,
  roles,
  busy,
  onEdit,
  onResetPassword,
  onToggleBlock,
  onDelete,
  onClose,
}: Props) {
  const insets = useSafeAreaInsets();
  const { tr } = useI18n();
  const name = user.name || user.displayName || user.email;
  const custom = roles.find((role) => role.id === user.role && !role.system);
  const roleKey = ROLE_LABEL[user.role];
  const roleText = custom?.name || (roleKey ? tr(roleKey) : user.role);
  const blocked = user.status === 'suspended' || user.status === 'inactive';

  return (
    <View style={[styles.sheet, { paddingBottom: Math.max(insets.bottom, 16) + spacing.md }]}>
      <View style={styles.handle} />
      <Pressable
        onPress={onClose}
        accessibilityRole="button"
        accessibilityLabel={tr('usersClose')}
        style={({ pressed }) => [styles.close, pressed && styles.pressed]}
      >
        <AppIcon icon={feather('x')} size={20} color={colors.textMuted} />
      </Pressable>

      <View style={styles.identity}>
        <UserAvatar name={name} email={user.email} size={48} />
        <View style={styles.identityMeta}>
          <Text style={styles.title}>{name}</Text>
          <View style={styles.identitySub}>
            <Text style={styles.email}>{user.email}</Text>
            <View style={styles.pill}>
              <Text style={styles.pillText}>{roleText}</Text>
            </View>
          </View>
        </View>
      </View>

      <View style={styles.box}>
        <SheetRow
          icon={<AppIcon icon={mci('account-edit-outline')} size={22} color={colors.accent} />}
          title={tr('usersEdit')}
          subtitle={tr('usersEditHint')}
          onPress={onEdit}
          disabled={busy}
        />
        <View style={styles.rowDivider} />
        <SheetRow
          icon={<AppIcon icon={ion('key-outline')} size={22} color={colors.accent} />}
          title={tr('usersResetPassword')}
          subtitle={tr('usersResetHint')}
          onPress={onResetPassword}
          disabled={busy}
        />
        <View style={styles.rowDivider} />
        <SheetRow
          icon={<AppIcon icon={mci('account-cancel-outline')} size={22} color={colors.accent} />}
          title={tr(blocked ? 'usersUnblock' : 'usersBlock')}
          subtitle={tr(blocked ? 'usersUnblockHint' : 'usersBlockHint')}
          onPress={onToggleBlock}
          disabled={busy}
        />
        <View style={styles.rowDivider} />
        <SheetRow
          icon={<AppIcon icon={feather('trash-2')} size={20} color={colors.danger} />}
          title={tr('usersDelete')}
          subtitle={tr('usersDeleteHint')}
          danger
          onPress={onDelete}
          disabled={busy}
        />
      </View>

      <Pressable
        onPress={onClose}
        accessibilityRole="button"
        accessibilityLabel={tr('usersCancel')}
        style={({ pressed }) => [styles.cancel, pressed && styles.pressed]}
      >
        <Text style={styles.cancelText}>{tr('usersCancel')}</Text>
      </Pressable>
    </View>
  );
}

function SheetRow({
  icon,
  title,
  subtitle,
  danger,
  disabled,
  onPress,
}: {
  icon: ReactNode;
  title: string;
  subtitle: string;
  danger?: boolean;
  disabled?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={title}
      style={({ pressed }) => [styles.row, pressed && styles.pressed]}
    >
      {icon}
      <View style={styles.rowText}>
        <Text style={[styles.rowTitle, danger && styles.danger]}>{title}</Text>
        <Text style={styles.rowSub}>{subtitle}</Text>
      </View>
      <AppIcon icon={feather('chevron-right')} size={18} color={colors.textDim} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radii.xl,
    borderTopRightRadius: radii.xl,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    gap: spacing.md,
  },
  handle: {
    alignSelf: 'center',
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#D4D8D8',
    marginBottom: 4,
  },
  close: {
    position: 'absolute',
    top: spacing.md,
    right: spacing.md,
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 2,
  },
  identity: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
    paddingRight: 36,
    marginTop: spacing.sm,
  },
  identityMeta: { flex: 1, gap: 4 },
  identitySub: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 8 },
  title: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 17, fontWeight: '700' },
  email: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 },
  pill: {
    backgroundColor: colors.accentSoft,
    borderRadius: radii.sm,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  pillText: { color: colors.accentDeep, fontFamily: fonts.bodyMedium, fontSize: 12 },
  box: { borderWidth: 1, borderColor: colors.border, borderRadius: 12, overflow: 'hidden' },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: 14,
  },
  rowDivider: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
  rowText: { flex: 1, gap: 2 },
  rowTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  rowSub: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 },
  danger: { color: colors.danger },
  cancel: {
    borderWidth: 1.5,
    borderColor: colors.accent,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: spacing.xs,
  },
  cancelText: { color: colors.accent, fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  pressed: { opacity: 0.55 },
});
