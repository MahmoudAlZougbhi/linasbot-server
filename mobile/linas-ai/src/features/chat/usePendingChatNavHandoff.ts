import { useEffect } from 'react';

import { useModuleNavOptional } from '../nav/ModuleNavContext';
import { takePendingChatNav } from './pendingChatNav';
import type { OwnerChatMode } from './ownerChatMode';

type OwnerNav = {
  loading: boolean;
  newChat: () => Promise<void> | void;
  openConversation: (id: string) => Promise<void>;
};

type TurnNav = {
  streaming: boolean;
  stop: () => void;
};

/**
 * Applies queued New Chat / Open Chat actions from module-screen drawers
 * once chat is active and the owner session has finished loading.
 * Compatible with keep-mounted Chat (re-runs when activeArea returns to chat).
 */
export function usePendingChatNavHandoff(opts: {
  isAuthenticated: boolean;
  owner: OwnerNav;
  turn: TurnNav;
  setOwnerMode: (mode: OwnerChatMode) => void;
  stickToBottom: () => void;
  afterOpen: () => void;
}) {
  const { isAuthenticated, owner, turn, setOwnerMode, stickToBottom, afterOpen } = opts;
  const nav = useModuleNavOptional();
  const activeArea = nav?.activeArea ?? null;
  const focusNonce = nav?.areaFocusNonce ?? 0;

  useEffect(() => {
    if (!isAuthenticated || owner.loading) return;
    if (activeArea !== 'chat') return;
    const pending = takePendingChatNav();
    if (!pending) return;
    stickToBottom();
    if (pending.type === 'new') {
      if (turn.streaming) turn.stop();
      setOwnerMode('chat');
      void owner.newChat();
      return;
    }
    void owner.openConversation(pending.conversationId).then(() => afterOpen());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, owner.loading, activeArea, focusNonce]);
}
