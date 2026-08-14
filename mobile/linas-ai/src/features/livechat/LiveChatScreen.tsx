import { useEffect, useRef, useState } from 'react';

import { useModuleNav } from '../nav/ModuleNavContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import { LiveChatInbox } from './LiveChatInbox';
import { LiveChatThread } from './LiveChatThread';
import type { LiveChatItem } from './liveChatTypes';
import { channelLabel, chatTitle } from './liveChatTypes';
import { useLiveChatInbox } from './useLiveChatInbox';

type Props = {
  /** Open a specific conversation (from owner notification deep link). */
  initialOpen?: { userId: string; conversationId: string } | null;
};

/**
 * Operator Live Chat inbox — same `/api/live-chat/*` APIs as the dashboard.
 * Completely separate from owner/guest Linas AI chat.
 * Thread → inbox: re-open Live Chat from the side menu (no Back chevron).
 */
export function LiveChatScreen({ initialOpen = null }: Props) {
  const inbox = useLiveChatInbox();
  const nav = useModuleNav();
  const [selected, setSelected] = useState<LiveChatItem | null>(null);
  const [deepLinkTried, setDeepLinkTried] = useState(false);
  const focusNonceSeen = useRef(nav.areaFocusNonce);

  useEffect(() => {
    if (nav.activeArea !== 'livechat') return;
    if (focusNonceSeen.current === nav.areaFocusNonce) return;
    focusNonceSeen.current = nav.areaFocusNonce;
    // Re-tapping Live Chat in the drawer returns to inbox (keep-mounted safe).
    setSelected(null);
    inbox.reloadQuiet();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reloadQuiet is stable enough; avoid inbox object churn
  }, [nav.areaFocusNonce, nav.activeArea]);

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
      <ScreenChrome title={chatTitle(selected)} subtitle={channelLabel(selected)}>
        <LiveChatThread chat={selected} onChatUpdated={inbox.reloadQuiet} />
      </ScreenChrome>
    );
  }

  return (
    <ScreenChrome title="Live Chat" subtitle="All customer conversations">
      <LiveChatInbox
        inbox={inbox}
        onOpenChat={(chat) => {
          setSelected(chat);
        }}
      />
    </ScreenChrome>
  );
}
