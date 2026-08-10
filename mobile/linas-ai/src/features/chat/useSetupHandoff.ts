import { useEffect, useRef } from 'react';

import type { OwnerChatMode } from './ownerChatMode';
import { takeSetupHandoff } from './pendingSetupHandoff';

type Args = {
  isAuthenticated: boolean;
  loading: boolean;
  streaming: boolean;
  setDraft: (text: string) => void;
  setOwnerMode: (mode: OwnerChatMode) => void;
  send: (text: string, mode: OwnerChatMode) => void | Promise<unknown>;
};

/** Consume CM → chat handoff once conversation is ready (Work mode + optional auto-send). */
export function useSetupHandoff({
  isAuthenticated,
  loading,
  streaming,
  setDraft,
  setOwnerMode,
  send,
}: Args): void {
  const handled = useRef(false);

  useEffect(() => {
    if (!isAuthenticated || loading || handled.current || streaming) return;
    const handoff = takeSetupHandoff();
    if (!handoff?.text) return;
    handled.current = true;
    setOwnerMode(handoff.mode);
    if (handoff.autoSend) {
      void send(handoff.text, handoff.mode);
      return;
    }
    setDraft(handoff.text);
  }, [isAuthenticated, loading, streaming, send, setDraft, setOwnerMode]);
}
