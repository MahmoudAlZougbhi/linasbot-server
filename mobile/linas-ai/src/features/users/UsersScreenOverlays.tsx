import { Pressable, StyleSheet } from 'react-native';

import { AppModal } from '../../components/AppModal';
import { ModalScrim } from '../../components/ModalScrim';
import { AuthGateModal } from '../auth/AuthGateModal';
import { UserActionSheet } from './UserActionSheet';
import { UserResetPasswordSheet } from './UserResetPasswordSheet';
import type { TeamUser } from './usersApi';
import type { TenantRole } from './usersRolesApi';

type Props = {
  menuUser: TeamUser | null;
  roles: TenantRole[];
  busy: boolean;
  resetUser: TeamUser | null;
  resetPassword: string;
  resetError: string | null;
  authGate: boolean;
  authBody: string;
  onCloseMenu: () => void;
  onEdit: () => void;
  onResetPassword: () => void;
  onToggleBlock: () => void;
  onDelete: () => void;
  onResetPasswordChange: (value: string) => void;
  onSaveReset: () => void;
  onCloseReset: () => void;
  onCloseAuth: () => void;
  onLogin: () => void;
  onRegister: () => void;
};

export function UsersScreenOverlays({
  menuUser,
  roles,
  busy,
  resetUser,
  resetPassword,
  resetError,
  authGate,
  authBody,
  onCloseMenu,
  onEdit,
  onResetPassword,
  onToggleBlock,
  onDelete,
  onResetPasswordChange,
  onSaveReset,
  onCloseReset,
  onCloseAuth,
  onLogin,
  onRegister,
}: Props) {
  return (
    <>
      <AppModal visible={menuUser !== null} animationType="fade" onRequestClose={onCloseMenu}>
        <ModalScrim onPress={onCloseMenu}>
          {menuUser ? (
            <Pressable style={styles.sheetWrap} onPress={(e) => e.stopPropagation()}>
              <UserActionSheet
                user={menuUser}
                roles={roles}
                busy={busy}
                onClose={onCloseMenu}
                onEdit={onEdit}
                onResetPassword={onResetPassword}
                onToggleBlock={onToggleBlock}
                onDelete={onDelete}
              />
            </Pressable>
          ) : null}
        </ModalScrim>
      </AppModal>

      <UserResetPasswordSheet
        visible={resetUser !== null}
        busy={busy}
        error={resetError}
        password={resetPassword}
        onPassword={onResetPasswordChange}
        onSave={onSaveReset}
        onClose={onCloseReset}
      />

      <AuthGateModal
        visible={authGate}
        reason={authBody}
        onClose={onCloseAuth}
        onLogin={onLogin}
        onRegister={onRegister}
      />
    </>
  );
}

const styles = StyleSheet.create({
  sheetWrap: { width: '100%' },
});
