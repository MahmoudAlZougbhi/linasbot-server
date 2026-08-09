import { useEffect, useState } from 'react';

import { ScreenChrome } from '../shared/ScreenChrome';
import { LiveChatInbox } from './LiveChatInbox';
import { LiveChatThread } from './LiveChatThread';
import type { LiveChatItem } from './liveChatTypes';
import { channelLabel, chatTitle } from './liveChatTypes';
import { useLiveChatInbox } from './useLiveChatInbox';

type Props = {
  onBack: () => void;
  /** Open a specific conversation (from owner notification deep link). */
  initialOpen?: { userId: string; conversationId: string } | null;
};

/**
 * Operator Live Chat inbox — same `/api/live-chat/*` APIs as the dashboard.
 * Completely separate from owner/guest Linas AI chat.
 */
export function LiveChatScreen({ onBack, initialOpen = null }: Props) {
  const inbox = useLiveChatInbox();
  const [selected, setSelected] = useState<LiveChatItem | null>(null);
  const [deepLinkTried, setDeepLinkTried] = useState(false);

  useEffect(() => {
    if (!initialOpen || deepLinkTried || inbox.loading) {
      return;
    }
    const match = inbox.chats.find(
      (c) =>
        c.user_id === initialOpen.userId && c.conversation_id === initialOpen.conversationId,
    );
    if (match) {
      setSelected(match);
      setDeepLinkTried(true);
      return;
    }
    // Conversation may not be on the first page — open a synthetic stub so the thread API loads.
    if (initialOpen.userId && initialOpen.conversationId) {
      setSelected({
        user_id: initialOpen.userId,
        conversation_id: initialOpen.conversationId,
        user_name: initialOpen.userId,
        status: 'waiting_human',
      });
      setDeepLinkTried(true);
    }
  }, [initialOpen, deepLinkTried, inbox.loading, inbox.chats]);

  if (selected) {
    return (
      <ScreenChrome
        title={chatTitle(selected)}
        subtitle={channelLabel(selected)}
        backLabel="← Inbox"
        onBack={() => {
          setSelected(null);
          inbox.reloadQuiet();
        }}
      >
        <LiveChatThread chat={selected} onChatUpdated={inbox.reloadQuiet} />
      </ScreenChrome>
    );
  }

  return (
    <ScreenChrome title="Live Chat" subtitle="Inbox — WhatsApp, Instagram, Facebook" onBack={onBack}>
      <LiveChatInbox
        inbox={inbox}
        onOpenChat={(chat) => {
          setSelected(chat);
        }}
      />
    </ScreenChrome>
  );
}
