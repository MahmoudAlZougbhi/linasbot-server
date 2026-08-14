import { StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import { UserOutlinedField } from './UserOutlinedField';
import { UserPasswordField } from './UserPasswordField';
import { UserRolePicker } from './UserRolePicker';
import type { TenantRole } from './usersRolesApi';

type Props = {
  name: string;
  email: string;
  password: string;
  roleId: string;
  roles: TenantRole[];
  emailLocked?: boolean;
  busy?: boolean;
  creatingRole?: boolean;
  onName: (value: string) => void;
  onEmail: (value: string) => void;
  onPassword: (value: string) => void;
  onRole: (roleId: string) => void;
  onCreateRole: (name: string) => void;
};

export function UserLoginCard({
  name,
  email,
  password,
  roleId,
  roles,
  emailLocked,
  busy,
  creatingRole,
  onName,
  onEmail,
  onPassword,
  onRole,
  onCreateRole,
}: Props) {
  const { tr } = useI18n();
  return (
    <View style={styles.card}>
      <Text style={styles.title}>{tr('usersLoginDetails')}</Text>
      <UserOutlinedField
        label={tr('usersName')}
        value={name}
        onChangeText={onName}
        autoCapitalize="words"
        editable={!busy}
      />
      <UserOutlinedField
        label={tr('email')}
        value={email}
        onChangeText={onEmail}
        autoCapitalize="none"
        keyboardType="email-address"
        editable={!busy && !emailLocked}
      />
      <UserPasswordField value={password} onChange={onPassword} editable={!busy} />
      <UserRolePicker
        roleId={roleId}
        roles={roles}
        disabled={busy}
        creating={creatingRole}
        onSelect={onRole}
        onCreate={onCreateRole}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: 4,
  },
  title: {
    fontFamily: fonts.bodyMedium,
    fontSize: 17,
    fontWeight: '700',
    color: colors.text,
    marginBottom: 8,
  },
});
