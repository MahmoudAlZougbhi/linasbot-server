import { useEffect, useState } from 'react';
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { TextField } from '../../components/TextField';
import { useI18n } from '../../i18n/LanguageContext';
import type { StringKey } from '../../i18n/locales/en';
import { colors, fonts, radii, spacing } from '../../theme';
import type { CreateUserInput, TeamUser, UpdateUserInput } from './usersApi';
import {
  ACCOUNT_STATUSES,
  ASSIGNABLE_ROLES,
  type AccountStatus,
  type AssignableRole,
  type PermissionKey,
  type PermissionMap,
  PERMISSION_KEYS,
  emptyPermissions,
  isAssignableRole,
  permissionsForRole,
  resolvePermissions,
} from './usersPermissions';

const PERM_LABEL: Record<PermissionKey, StringKey> = {
  dashboard: 'permDashboard',
  liveChat: 'permLiveChat',
  training: 'permTraining',
  testing: 'permTesting',
  analytics: 'permAnalytics',
  smartMessaging: 'permSmartMessaging',
  settings: 'permSettings',
  userManagement: 'permUserManagement',
  contentManagers: 'permContentManagers',
  contentPublish: 'permContentPublish',
  activityFlow: 'permActivityFlow',
};

const ROLE_LABEL: Record<AssignableRole, StringKey> = {
  admin: 'roleAdmin',
  operator: 'roleOperator',
  viewer: 'roleViewer',
};

const STATUS_LABEL: Record<AccountStatus, StringKey> = {
  active: 'statusActive',
  inactive: 'statusInactive',
  suspended: 'statusSuspended',
};

type Props = {
  visible: boolean;
  user: TeamUser | null;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onCreate: (input: CreateUserInput) => void;
  onUpdate: (userId: string, input: UpdateUserInput) => void;
};

export function UserFormModal({ visible, user, busy, error, onClose, onCreate, onUpdate }: Props) {
  const { tr } = useI18n();
  const isEditing = Boolean(user);
  const roleLocked = user?.role === 'platform_owner';

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<AssignableRole>('viewer');
  const [status, setStatus] = useState<AccountStatus>('active');
  const [useCustom, setUseCustom] = useState(false);
  const [permissions, setPermissions] = useState<PermissionMap>(emptyPermissions());
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    setLocalError(null);
    if (user) {
      setName(user.name || user.displayName || '');
      setEmail(user.email);
      setPassword('');
      setRole(isAssignableRole(user.role) ? user.role : 'viewer');
      setStatus(
        user.status === 'inactive' || user.status === 'suspended' ? user.status : 'active',
      );
      const hasCustom = Boolean(user.permissions);
      setUseCustom(hasCustom);
      setPermissions(resolvePermissions(user.role, user.permissions ?? null));
    } else {
      setName('');
      setEmail('');
      setPassword('');
      setRole('viewer');
      setStatus('active');
      setUseCustom(false);
      setPermissions(permissionsForRole('viewer'));
    }
  }, [visible, user]);

  useEffect(() => {
    if (!useCustom) {
      setPermissions(permissionsForRole(role));
    }
  }, [role, useCustom]);

  function togglePerm(key: PermissionKey, value: boolean) {
    setPermissions((prev) => ({ ...prev, [key]: value }));
  }

  function submit() {
    setLocalError(null);
    const trimmedName = name.trim();
    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedName) {
      setLocalError(tr('usersNameRequired'));
      return;
    }
    if (!isEditing) {
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
        role,
        status,
        permissions: useCustom ? permissions : null,
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
      status,
      permissions: useCustom ? permissions : null,
    };
    if (!roleLocked) {
      updates.role = role;
    }
    if (password) {
      updates.password = password;
    }
    onUpdate(user.id, updates);
  }

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={styles.wrap}>
        <View style={styles.head}>
          <Text style={styles.title}>{isEditing ? tr('usersEditTitle') : tr('usersAddTitle')}</Text>
          <Pressable onPress={onClose} hitSlop={12}>
            <Text style={styles.close}>{tr('usersClose')}</Text>
          </Pressable>
        </View>

        <ScrollView contentContainerStyle={styles.form} keyboardShouldPersistTaps="handled">
          <Text style={styles.label}>{tr('usersName')}</Text>
          <TextField value={name} onChangeText={setName} autoCapitalize="words" editable={!busy} />

          <Text style={styles.label}>{tr('email')}</Text>
          <TextField
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
            editable={!busy && !isEditing}
          />

          <Text style={styles.label}>
            {isEditing ? tr('usersPasswordOptional') : tr('password')}
          </Text>
          <TextField
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoCapitalize="none"
            editable={!busy}
            placeholder={isEditing ? tr('usersPasswordKeep') : undefined}
          />

          <Text style={styles.label}>{tr('usersRole')}</Text>
          {roleLocked ? (
            <Text style={styles.locked}>{tr('rolePlatformOwner')}</Text>
          ) : (
            <View style={styles.chipRow}>
              {ASSIGNABLE_ROLES.map((r) => (
                <Pressable
                  key={r}
                  style={[styles.chip, role === r && styles.chipOn]}
                  onPress={() => setRole(r)}
                  disabled={busy}
                >
                  <Text style={[styles.chipText, role === r && styles.chipTextOn]}>{tr(ROLE_LABEL[r])}</Text>
                </Pressable>
              ))}
            </View>
          )}

          <Text style={styles.label}>{tr('usersStatus')}</Text>
          <View style={styles.chipRow}>
            {ACCOUNT_STATUSES.map((s) => (
              <Pressable
                key={s}
                style={[styles.chip, status === s && styles.chipOn]}
                onPress={() => setStatus(s)}
                disabled={busy}
              >
                <Text style={[styles.chipText, status === s && styles.chipTextOn]}>
                  {tr(STATUS_LABEL[s])}
                </Text>
              </Pressable>
            ))}
          </View>

          <View style={styles.customRow}>
            <Text style={styles.labelInline}>{tr('usersCustomPerms')}</Text>
            <Switch
              value={useCustom}
              onValueChange={setUseCustom}
              disabled={busy || roleLocked}
              trackColor={{ false: colors.border, true: colors.lavender }}
              thumbColor={useCustom ? colors.accent : colors.surfaceAlt}
            />
          </View>
          {!useCustom ? <Text style={styles.hint}>{tr('usersPermsInherited')}</Text> : null}

          {PERMISSION_KEYS.map((key) => (
            <View key={key} style={styles.permRow}>
              <Text style={styles.permLabel}>{tr(PERM_LABEL[key])}</Text>
              <Switch
                value={permissions[key]}
                onValueChange={(v) => togglePerm(key, v)}
                disabled={!useCustom || busy || roleLocked}
                trackColor={{ false: colors.border, true: colors.lavender }}
                thumbColor={permissions[key] ? colors.accent : colors.surfaceAlt}
              />
            </View>
          ))}

          {localError || error ? <Text style={styles.error}>{localError || error}</Text> : null}

          <PrimaryButton
            label={isEditing ? tr('usersSave') : tr('usersCreate')}
            onPress={submit}
            loading={busy}
            disabled={busy}
            style={styles.submit}
          />
          <PrimaryButton label={tr('usersCancel')} onPress={onClose} variant="ghost" disabled={busy} />
        </ScrollView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.bg },
  head: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xl,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  title: { fontFamily: fonts.bodyMedium, fontSize: 20, color: colors.text },
  close: { color: colors.accent, fontFamily: fonts.bodyMedium, fontSize: 15 },
  form: { padding: spacing.lg, paddingBottom: 48 },
  label: {
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    color: colors.textMuted,
    marginBottom: 6,
  },
  labelInline: { fontFamily: fonts.bodyMedium, fontSize: 14, color: colors.text, flex: 1 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: spacing.md },
  chip: {
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  chipOn: { backgroundColor: colors.accentSoft, borderColor: colors.accent },
  chipText: { fontFamily: fonts.body, fontSize: 13, color: colors.textMuted },
  chipTextOn: { color: colors.accentDeep, fontFamily: fonts.bodyMedium },
  locked: {
    fontFamily: fonts.body,
    color: colors.textMuted,
    marginBottom: spacing.md,
    fontSize: 14,
  },
  customRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.sm,
    marginBottom: spacing.sm,
    gap: 12,
  },
  hint: {
    fontFamily: fonts.body,
    fontSize: 12,
    color: colors.textDim,
    marginBottom: spacing.md,
  },
  permRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.borderSoft,
  },
  permLabel: { fontFamily: fonts.body, fontSize: 14, color: colors.text, flex: 1, paddingRight: 12 },
  error: { color: colors.danger, fontFamily: fonts.body, marginVertical: spacing.md },
  submit: { marginTop: spacing.lg, marginBottom: spacing.sm },
});
