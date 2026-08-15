import { AuthGateModal } from '../auth/AuthGateModal';
import type { ControlArea } from '../control/controlAreas';
import type { HistoryItem } from '../nav/HistoryRows';
import { NavDrawer } from '../nav/NavDrawer';
import { ComposerPlusMenu, type PlusAction } from './ComposerPlusMenu';
import { handlePlusAction } from './handlePlusAction';
import type { PendingFile } from './v2/pickAttachment';

type Props = {
  drawerOpen: boolean;
  onCloseDrawer: () => void;
  isAuthenticated: boolean;
  activeArea?: ControlArea | 'chat' | null;
  history: HistoryItem[];
  archivedIds: string[];
  pinnedIds: string[];
  activeId: string | null;
  workspaceLabel: string | null;
  onOpenArea: (area: ControlArea) => void;
  onNewChat: () => void;
  onOpenChat: (id: string) => void;
  onTogglePin: (id: string) => void;
  onArchive: (id: string) => void;
  onUnarchive: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onLogin: () => void;
  onRegister: () => void;
  plusOpen: boolean;
  onClosePlus: () => void;
  pendingFiles: PendingFile[];
  setPendingFiles: (files: PendingFile[] | ((prev: PendingFile[]) => PendingFile[])) => void;
  authGate: boolean;
  hardLimit: boolean;
  guestGated: boolean;
  gateText?: string | null;
  onCloseAuth: () => void;
  onRequestLogin: () => void;
  onRequestRegister: () => void;
};

export function ChatScreenOverlays(props: Props) {
  return (
    <>
      <NavDrawer
        open={props.drawerOpen}
        onClose={props.onCloseDrawer}
        isAuthenticated={props.isAuthenticated}
        showUsers={props.isAuthenticated}
        activeArea={props.activeArea ?? 'chat'}
        history={props.history}
        archivedIds={props.archivedIds}
        pinnedIds={props.pinnedIds}
        activeId={props.activeId}
        workspaceLabel={props.workspaceLabel}
        onOpenArea={props.onOpenArea}
        onNewChat={props.onNewChat}
        onOpenChat={props.onOpenChat}
        onTogglePin={props.onTogglePin}
        onArchive={props.onArchive}
        onUnarchive={props.onUnarchive}
        onRename={props.onRename}
        onDelete={props.onDelete}
        onLogin={props.onLogin}
        onRegister={props.onRegister}
      />

      {props.isAuthenticated ? (
        <ComposerPlusMenu
          open={props.plusOpen}
          onClose={props.onClosePlus}
          onAction={(a: PlusAction) =>
            void handlePlusAction({
              action: a,
              isAuthenticated: props.isAuthenticated,
              pendingFiles: props.pendingFiles,
              setPendingFiles: props.setPendingFiles,
            })
          }
        />
      ) : null}

      <AuthGateModal
        visible={props.authGate}
        hardLimit={props.hardLimit || props.guestGated}
        reason={props.gateText ?? undefined}
        onClose={props.onCloseAuth}
        onLogin={() => {
          props.onCloseAuth();
          props.onRequestLogin();
        }}
        onRegister={() => {
          props.onCloseAuth();
          props.onRequestRegister();
        }}
      />
    </>
  );
}
