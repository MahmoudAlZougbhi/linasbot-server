import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import type { PublicUser } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { tokenStore } from '../../auth/tokenStore';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import { AuthGateModal } from '../auth/AuthGateModal';
import { useModuleNav } from '../nav/ModuleNavContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import { UserActionSheet } from './UserActionSheet';
import { UserFormScreen } from './UserFormScreen';
import { UserListRow } from './UserListRow';
import { UserResetPasswordSheet } from './UserResetPasswordSheet';
import { UsersSearchBar } from './UsersSearchBar';
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
import { canManageUsers } from './usersPermissions';
import { listRoles, type TenantRole } from './usersRolesApi';

type Props = {
  onRequestLogin?: () => void;
  onRequestRegister?: () => void;
};

type Gate = 'none' | 'auth' | 'forbidden';

export function UsersScreen({ onRequestLogin, onRequestRegister }: Props) {
  const { tr } = useI18n();
  const nav = useModuleNav();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [users, setUsers] = useState<TeamUser[]>([]);
  const [roles, setRoles] = useState<TenantRole[]>([]);
  const [me, setMe] = useState<PublicUser | null>(null);
  const [gate, setGate] = useState<Gate>('none');
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<TeamUser | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [menuUser, setMenuUser] = useState<TeamUser | null>(null);
  const [resetUser, setResetUser] = useState<TeamUser | null>(null);
  const [resetPassword, setResetPassword] = useState('');
  const [resetError, setResetError] = useState<string | null>(null);
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
      const [list, roleList] = await Promise.all([listUsers(), listRoles()]);
      setUsers(list);
      setRoles(roleList);
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

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return users;
    return users.filter((user) => {
      const name = (user.name || user.displayName || '').toLowerCase();
      return name.includes(q) || user.email.toLowerCase().includes(q) || user.role.toLowerCase().includes(q);
    });
  }, [users, query]);

  const activeCount = users.filter((user) => user.status === 'active').length;
  const summary =
    users.length === 1
      ? tr('usersSummaryOne').replace('{a}', String(activeCount))
      : tr('usersSummary').replace('{n}', String(users.length)).replace('{a}', String(activeCount));

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
      { text: tr('usersDelete'), style: 'destructive', onPress: () => void runDelete(user.id) },
    ]);
  }

  async function runDelete(userId: string) {
    setBusy(true);
    setError(null);
    try {
      await deleteUser(userId);
      setMenuUser(null);
      await load();
    } catch (err) {
      setError(usersErrorMessage(err, tr('usersDeleteError')));
    } finally {
      setBusy(false);
    }
  }

  async function toggleBlock(user: TeamUser) {
    setBusy(true);
    try {
      const blocked = user.status === 'suspended' || user.status === 'inactive';
      await updateUser(user.id, { status: blocked ? 'active' : 'suspended' });
      setMenuUser(null);
      await load();
    } catch (err) {
      setError(usersErrorMessage(err, tr('usersUpdateError')));
    } finally {
      setBusy(false);
    }
  }

  async function saveReset() {
    if (!resetUser) return;
    if (!resetPassword || resetPassword.length < 8) {
      setResetError(tr('usersPasswordMin'));
      return;
    }
    setBusy(true);
    setResetError(null);
    try {
      await updateUser(resetUser.id, { password: resetPassword });
      setResetUser(null);
      setResetPassword('');
    } catch (err) {
      setResetError(usersErrorMessage(err, tr('usersUpdateError')));
    } finally {
      setBusy(false);
    }
  }

  const showList = gate === 'none' && !authGate;

  if (formOpen) {
    return (
      <UserFormScreen
        user={editing}
        roles={roles}
        busy={busy}
        error={formError}
        onRolesChange={setRoles}
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
    );
  }

  return (
    <ScreenChrome
      title={tr('usersTitle')}
      subtitle={tr('usersSub')}
      headerRight={
        showList ? (
          <Pressable
            onPress={() => {
              setEditing(null);
              setFormError(null);
              setFormOpen(true);
            }}
            disabled={busy}
            accessibilityRole="button"
            accessibilityLabel={tr('usersAdd')}
            style={({ pressed }) => [styles.addPill, pressed && styles.pressed]}
          >
            <Text style={styles.addText}>{tr('usersAdd')}</Text>
          </Pressable>
        ) : undefined
      }
    >
      {loading ? <ActivityIndicator color={colors.accent} style={styles.spinner} /> : null}
      {!loading && authGate ? <EmptyState title={tr('authGateTitle')} body={tr('usersAuthBody')} /> : null}
      {!loading && gate === 'forbidden' ? (
        <EmptyState title={tr('usersForbiddenTitle')} body={tr('usersForbiddenBody')} />
      ) : null}

      {!loading && showList ? (
        <>
          <Text style={styles.summary}>
            {summary.split(' · ')[0]}
            {' · '}
            <Text style={styles.activeCount}>{summary.split(' · ')[1]}</Text>
          </Text>
          <UsersSearchBar value={query} onChange={setQuery} />
          {error ? (
            <Text style={styles.error} onPress={() => void load()}>
              {error}
            </Text>
          ) : null}
          <ScrollView contentContainerStyle={styles.list}>
            {filtered.length === 0 && !error ? (
              <EmptyState title={tr('usersEmptyTitle')} body={tr('usersEmptyBody')} />
            ) : (
              <View style={styles.card}>
                {filtered.map((user, index) => (
                  <UserListRow
                    key={user.id}
                    user={user}
                    roles={roles}
                    last={index === filtered.length - 1}
                    disabled={busy}
                    onMenu={() => setMenuUser(user)}
                  />
                ))}
              </View>
            )}
          </ScrollView>
        </>
      ) : null}

      <Modal visible={menuUser !== null} transparent animationType="fade" onRequestClose={() => setMenuUser(null)}>
        <Pressable style={styles.scrim} onPress={() => setMenuUser(null)}>
          {menuUser ? (
            <Pressable style={styles.sheetWrap} onPress={(e) => e.stopPropagation()}>
              <UserActionSheet
                user={menuUser}
                roles={roles}
                busy={busy}
                onClose={() => setMenuUser(null)}
                onEdit={() => {
                  setEditing(menuUser);
                  setFormError(null);
                  setMenuUser(null);
                  setFormOpen(true);
                }}
                onResetPassword={() => {
                  setResetUser(menuUser);
                  setResetPassword('');
                  setResetError(null);
                  setMenuUser(null);
                }}
                onToggleBlock={() => void toggleBlock(menuUser)}
                onDelete={() => confirmDelete(menuUser)}
              />
            </Pressable>
          ) : null}
        </Pressable>
      </Modal>

      <UserResetPasswordSheet
        visible={resetUser !== null}
        busy={busy}
        error={resetError}
        password={resetPassword}
        onPassword={setResetPassword}
        onSave={() => void saveReset()}
        onClose={() => {
          if (!busy) {
            setResetUser(null);
            setResetPassword('');
            setResetError(null);
          }
        }}
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
  addPill: {
    backgroundColor: colors.accent,
    borderRadius: radii.pill,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  addText: { color: colors.onAccent, fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '700' },
  summary: { fontFamily: fonts.body, fontSize: 14, color: colors.textMuted, marginBottom: 12 },
  activeCount: { color: colors.accent, fontFamily: fonts.bodyMedium },
  list: { paddingBottom: 40, paddingTop: 12, gap: spacing.md },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: 'hidden',
  },
  error: { color: colors.danger, fontFamily: fonts.body, fontSize: 14, marginTop: 8 },
  scrim: { flex: 1, justifyContent: 'flex-end', backgroundColor: colors.overlay },
  sheetWrap: { width: '100%' },
  pressed: { opacity: 0.55 },
});
