import { useEffect, useRef } from 'react';

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
    const id = setInterval(() => {
      void markConversationRead(userId, conversationId);
    }, HEARTBEAT_MS);
    return () => clearInterval(id);
  }, [userId, conversationId]);
}
