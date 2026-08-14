import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { GradientBackground } from '../../components/GradientBackground';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import { UserAccessGrid } from './UserAccessGrid';
import { UserFormHeader } from './UserFormHeader';
import { UserLoginCard } from './UserLoginCard';
import { mapsEqual } from './usersAccess';
import type { CreateUserInput, TeamUser, UpdateUserInput } from './usersApi';
import {
  permissionsForRole,
  permissionsFromRecord,
  type PermissionMap,
} from './usersPermissions';
import { createRole, type TenantRole } from './usersRolesApi';

type Props = {
  user: TeamUser | null;
  roles: TenantRole[];
  busy: boolean;
  error: string | null;
  onRolesChange: (roles: TenantRole[]) => void;
  onClose: () => void;
  onCreate: (input: CreateUserInput) => void;
  onUpdate: (userId: string, input: UpdateUserInput) => void;
};

export function UserFormScreen({
  user,
  roles,
  busy,
  error,
  onRolesChange,
  onClose,
  onCreate,
  onUpdate,
}: Props) {
  const { tr } = useI18n();
  const editing = Boolean(user);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [roleId, setRoleId] = useState('operator');
  const [permissions, setPermissions] = useState<PermissionMap>(permissionsForRole('operator'));
  const [localError, setLocalError] = useState<string | null>(null);
  const [creatingRole, setCreatingRole] = useState(false);

  useEffect(() => {
    setLocalError(null);
    if (user) {
      setName(user.name || user.displayName || '');
      setEmail(user.email);
      setPassword('');
      const nextRole = user.role === 'platform_owner' ? 'admin' : user.role;
      setRoleId(nextRole);
      const catalog = roles.find((role) => role.id === nextRole);
      setPermissions(
        user.permissions
          ? permissionsFromRecord(user.permissions)
          : catalog
            ? permissionsFromRecord(catalog.permissions)
            : permissionsForRole(nextRole),
      );
      return;
    }
    setName('');
    setEmail('');
    setPassword('');
    setRoleId('operator');
    setPermissions(permissionsForRole('operator'));
  }, [user]);

  function applyRole(nextId: string) {
    setRoleId(nextId);
    const catalog = roles.find((role) => role.id === nextId);
    setPermissions(
      catalog ? permissionsFromRecord(catalog.permissions) : permissionsForRole(nextId),
    );
  }

  async function handleCreateRole(roleName: string) {
    setCreatingRole(true);
    setLocalError(null);
    try {
      const role = await createRole({ name: roleName, permissions });
      onRolesChange([...roles.filter((item) => item.id !== role.id), role]);
      setRoleId(role.id);
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : tr('usersRoleCreateError'));
    } finally {
      setCreatingRole(false);
    }
  }

  function submit() {
    setLocalError(null);
    const trimmedName = name.trim();
    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedName) {
      setLocalError(tr('usersNameRequired'));
      return;
    }
    const catalog = roles.find((role) => role.id === roleId);
    const template = catalog
      ? permissionsFromRecord(catalog.permissions)
      : permissionsForRole(roleId);
    const custom = !mapsEqual(permissions, template);
    const payloadPerms = catalog && !catalog.system ? permissions : custom ? permissions : null;
    if (!editing) {
      if (!trimmedEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
        setLocalError(tr('usersEmailInvalid'));
        return;
      }
      if (!password || password.length < 8) {
        setLocalError(tr('usersPasswordMin'));
        return;
      }
      onCreate({
        email: trimmedEmail,
        password,
        name: trimmedName,
        role: roleId,
        status: 'active',
        permissions: payloadPerms,
      });
      return;
    }
    if (!user) return;
    if (password && password.length < 8) {
      setLocalError(tr('usersPasswordMin'));
      return;
    }
    const updates: UpdateUserInput = {
      name: trimmedName,
      permissions: payloadPerms,
    };
    if (user.role !== 'platform_owner') updates.role = roleId;
    if (password) updates.password = password;
    onUpdate(user.id, updates);
  }

  return (
    <GradientBackground>
      <UserFormHeader
        title={editing ? tr('usersEditTitle') : tr('usersAddTitle')}
        subtitle={editing ? tr('usersEditSub') : tr('usersAddSub')}
        onBack={onClose}
      />
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={styles.form} keyboardShouldPersistTaps="handled">
          <UserLoginCard
            name={name}
            email={email}
            password={password}
            roleId={roleId}
            roles={roles}
            emailLocked={editing}
            busy={busy}
            creatingRole={creatingRole}
            onName={setName}
            onEmail={setEmail}
            onPassword={setPassword}
            onRole={applyRole}
            onCreateRole={(value) => void handleCreateRole(value)}
          />
          <View style={styles.card}>
            <UserAccessGrid
              permissions={permissions}
              onChange={setPermissions}
              disabled={busy || roleId === 'admin'}
            />
          </View>
          {localError || error ? <Text style={styles.error}>{localError || error}</Text> : null}
          <PrimaryButton
            label={editing ? tr('usersSave') : tr('usersCreate')}
            onPress={submit}
            loading={busy}
            disabled={busy}
          />
          <Pressable onPress={onClose} disabled={busy} style={styles.cancelWrap}>
            <Text style={styles.cancel}>{tr('usersCancel')}</Text>
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  form: { paddingHorizontal: spacing.lg, paddingBottom: 48, gap: spacing.md },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
  },
  error: { color: colors.danger, fontFamily: fonts.body, fontSize: 14 },
  cancelWrap: { alignItems: 'center', paddingVertical: 8 },
  cancel: { color: colors.accent, fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
});
