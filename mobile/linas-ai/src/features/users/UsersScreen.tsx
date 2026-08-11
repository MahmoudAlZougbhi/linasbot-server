import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import type { PublicUser } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { PrimaryButton } from '../../components/PrimaryButton';
import { StatusChip } from '../../components/StatusChip';
import { tokenStore } from '../../auth/tokenStore';
import { useI18n } from '../../i18n/LanguageContext';
import type { StringKey } from '../../i18n/locales/en';
import { colors, fonts, radii, spacing } from '../../theme';
import { AuthGateModal } from '../auth/AuthGateModal';
import { useModuleNav } from '../nav/ModuleNavContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import { UserFormModal } from './UserFormModal';
import {
  classifyUsersError,
  createUser,
  deleteUser,
  listUsers,
  type CreateUserInput,
  type TeamUser,
  type UpdateUserInput,
  updateUser,
  usersErrorMessage,
} from './usersApi';
import { canManageUsers, isAssignableRole } from './usersPermissions';

type Props = {
  onRequestLogin?: () => void;
  onRequestRegister?: () => void;
};

type Gate = 'none' | 'auth' | 'forbidden';

const ROLE_LABEL: Record<string, StringKey> = {
  admin: 'roleAdmin',
  operator: 'roleOperator',
  viewer: 'roleViewer',
  platform_owner: 'rolePlatformOwner',
};

function statusTone(status: string | null | undefined): 'ok' | 'warn' | 'neutral' {
  if (status === 'active') return 'ok';
  if (status === 'suspended') return 'warn';
  return 'neutral';
}

function statusLabelKey(status: string | null | undefined): StringKey {
  if (status === 'active') return 'statusActive';
  if (status === 'suspended') return 'statusSuspended';
  return 'statusInactive';
}

export function UsersScreen({ onRequestLogin, onRequestRegister }: Props) {
  const { tr } = useI18n();
  const nav = useModuleNav();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [users, setUsers] = useState<TeamUser[]>([]);
  const [me, setMe] = useState<PublicUser | null>(null);
  const [gate, setGate] = useState<Gate>('none');
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<TeamUser | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [authGate, setAuthGate] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const access = await tokenStore.getAccessToken();
      const user = await tokenStore.getUser();
      setMe(user);
      if (!access) {
        setAuthGate(true);
        setGate('auth');
        setUsers([]);
        return;
      }
      if (!canManageUsers(user)) {
        setGate('forbidden');
        setUsers([]);
        return;
      }
      setGate('none');
      const list = await listUsers();
      setUsers(list);
    } catch (err) {
      const kind = classifyUsersError(err);
      if (kind === 'auth') {
        setAuthGate(true);
        setGate('auth');
        setUsers([]);
        setError(null);
      } else if (kind === 'forbidden') {
        setGate('forbidden');
        setUsers([]);
        setError(null);
      } else {
        setGate('none');
        setError(usersErrorMessage(err, tr('usersLoadError')));
        setUsers([]);
      }
    } finally {
      setLoading(false);
    }
  }, [tr]);

  useEffect(() => {
    void load();
  }, [load]);

  function openCreate() {
    setEditing(null);
    setFormError(null);
    setFormOpen(true);
  }

  function openEdit(user: TeamUser) {
    setEditing(user);
    setFormError(null);
    setFormOpen(true);
  }

  async function handleCreate(input: CreateUserInput) {
    setBusy(true);
    setFormError(null);
    try {
      await createUser(input);
      setFormOpen(false);
      await load();
    } catch (err) {
      setFormError(usersErrorMessage(err, tr('usersCreateError')));
    } finally {
      setBusy(false);
    }
  }

  async function handleUpdate(userId: string, input: UpdateUserInput) {
    setBusy(true);
    setFormError(null);
    try {
      await updateUser(userId, input);
      setFormOpen(false);
      setEditing(null);
      await load();
    } catch (err) {
      setFormError(usersErrorMessage(err, tr('usersUpdateError')));
    } finally {
      setBusy(false);
    }
  }

  function confirmDelete(user: TeamUser) {
    if (me?.id && user.id === me.id) {
      Alert.alert(tr('usersDeleteTitle'), tr('usersCannotDeleteSelf'));
      return;
    }
    Alert.alert(tr('usersDeleteTitle'), tr('usersDeleteConfirm'), [
      { text: tr('usersCancel'), style: 'cancel' },
      {
        text: tr('usersDelete'),
        style: 'destructive',
        onPress: () => void runDelete(user.id),
      },
    ]);
  }

  async function runDelete(userId: string) {
    setBusy(true);
    setError(null);
    try {
      await deleteUser(userId);
      await load();
    } catch (err) {
      setError(usersErrorMessage(err, tr('usersDeleteError')));
    } finally {
      setBusy(false);
    }
  }

  const showList = gate === 'none' && !authGate;

  return (
    <ScreenChrome title={tr('usersTitle')} subtitle={tr('usersSub')}>
      {loading ? <ActivityIndicator color={colors.accent} style={styles.spinner} /> : null}

      {!loading && authGate ? (
        <EmptyState title={tr('authGateTitle')} body={tr('usersAuthBody')} />
      ) : null}

      {!loading && gate === 'forbidden' ? (
        <EmptyState title={tr('usersForbiddenTitle')} body={tr('usersForbiddenBody')} />
      ) : null}

      {!loading && showList ? (
        <>
          <View style={styles.toolbar}>
            <Text style={styles.count}>
              {users.length === 1
                ? tr('usersCountOne')
                : tr('usersCountMany').replace('{n}', String(users.length))}
            </Text>
            <PrimaryButton label={tr('usersAdd')} onPress={openCreate} disabled={busy} style={styles.addBtn} />
          </View>

          {error ? (
            <View style={styles.errorBox}>
              <Text style={styles.error}>{error}</Text>
              <PrimaryButton label={tr('usersRetry')} onPress={() => void load()} variant="ghost" />
            </View>
          ) : null}

          <ScrollView contentContainerStyle={styles.list}>
            {users.length === 0 && !error ? (
              <EmptyState title={tr('usersEmptyTitle')} body={tr('usersEmptyBody')} />
            ) : null}
            {users.map((user) => {
              const roleKey = ROLE_LABEL[user.role];
              const roleText = roleKey ? tr(roleKey) : user.role;
              const isSelf = Boolean(me?.id && user.id === me.id);
              return (
                <View key={user.id} style={styles.card}>
                  <View style={styles.cardTop}>
                    <View style={styles.cardMeta}>
                      <Text style={styles.name}>{user.name || user.displayName || user.email}</Text>
                      <Text style={styles.email}>{user.email}</Text>
                    </View>
                    <StatusChip label={tr(statusLabelKey(user.status))} tone={statusTone(user.status)} />
                  </View>
                  <View style={styles.metaRow}>
                    <StatusChip label={roleText} tone="neutral" />
                    {user.permissions ? <StatusChip label={tr('usersCustomBadge')} tone="soon" /> : null}
                    {isSelf ? <StatusChip label={tr('usersYou')} tone="ok" /> : null}
                  </View>
                  <View style={styles.actions}>
                    <Pressable style={styles.actionBtn} onPress={() => openEdit(user)} disabled={busy}>
                      <Text style={styles.actionText}>{tr('usersEdit')}</Text>
                    </Pressable>
                    <Pressable
                      style={styles.actionBtn}
                      onPress={() => confirmDelete(user)}
                      disabled={busy || isSelf}
                    >
                      <Text style={[styles.actionText, styles.dangerText]}>{tr('usersDelete')}</Text>
                    </Pressable>
                  </View>
                  {!isAssignableRole(user.role) && user.role !== 'platform_owner' ? (
                    <Text style={styles.roleNote}>{tr('usersUnknownRole')}</Text>
                  ) : null}
                </View>
              );
            })}
          </ScrollView>
        </>
      ) : null}

      <UserFormModal
        visible={formOpen}
        user={editing}
        busy={busy}
        error={formError}
        onClose={() => {
          if (!busy) {
            setFormOpen(false);
            setEditing(null);
            setFormError(null);
          }
        }}
        onCreate={(input) => void handleCreate(input)}
        onUpdate={(id, input) => void handleUpdate(id, input)}
      />

      <AuthGateModal
        visible={authGate}
        reason={tr('usersAuthBody')}
        onClose={nav.goChat}
        onLogin={() => {
          setAuthGate(false);
          onRequestLogin?.();
        }}
        onRegister={() => {
          setAuthGate(false);
          onRequestRegister?.();
        }}
      />
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  spinner: { marginTop: spacing.xl },
  toolbar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
    gap: spacing.md,
  },
  count: { fontFamily: fonts.body, color: colors.textMuted, flex: 1, fontSize: 14 },
  addBtn: { paddingVertical: spacing.sm + 2, paddingHorizontal: spacing.md },
  list: { paddingBottom: 40, gap: spacing.md },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', gap: spacing.md },
  cardMeta: { flex: 1 },
  name: { fontFamily: fonts.bodyMedium, fontSize: 16, color: colors.text },
  email: { fontFamily: fonts.body, fontSize: 13, color: colors.textMuted, marginTop: 2 },
  metaRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  actions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.xs },
  actionBtn: { paddingVertical: 6 },
  actionText: { fontFamily: fonts.bodyMedium, color: colors.accent, fontSize: 14 },
  dangerText: { color: colors.danger },
  roleNote: { fontFamily: fonts.body, fontSize: 12, color: colors.textDim },
  errorBox: { marginBottom: spacing.md, gap: spacing.sm },
  error: { color: colors.danger, fontFamily: fonts.body, fontSize: 14 },
});
