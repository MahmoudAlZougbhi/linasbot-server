import { useEffect, useRef } from 'react';
import { AppState } from 'react-native';

import { markConversationRead } from './liveChatApi';

const HEARTBEAT_MS = 30_000;

/** Mark the thread read on open; heartbeat while it stays open. Does not pause AI. */
export function useLiveChatOperatorPresence(
  userId: string,
  conversationId: string,
  onOpen: () => void,
) {
  const openedKey = useRef('');
  const onOpenRef = useRef(onOpen);
  onOpenRef.current = onOpen;

  useEffect(() => {
    const key = `${userId}:${conversationId}`;
    if (!userId || !conversationId || openedKey.current === key) return;
    openedKey.current = key;
    onOpenRef.current();
  }, [userId, conversationId]);

  useEffect(() => {
    if (!userId || !conversationId) return;
    let id: ReturnType<typeof setInterval> | null = null;
    const start = () => {
      if (id) return;
      id = setInterval(() => {
        void markConversationRead(userId, conversationId);
      }, HEARTBEAT_MS);
    };
    const stop = () => {
      if (!id) return;
      clearInterval(id);
      id = null;
    };
    if (AppState.currentState === 'active') start();
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') start();
      else stop();
    });
    return () => {
      stop();
      sub.remove();
    };
  }, [userId, conversationId]);
}
