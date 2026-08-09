import { useState } from 'react';

import { ScreenChrome } from '../shared/ScreenChrome';
import { LiveChatInbox } from './LiveChatInbox';
import { LiveChatThread } from './LiveChatThread';
import type { LiveChatItem } from './liveChatTypes';
import { channelLabel, chatTitle } from './liveChatTypes';
import { useLiveChatInbox } from './useLiveChatInbox';

type Props = { onBack: () => void };

/**
 * Operator Live Chat inbox — same `/api/live-chat/*` APIs as the dashboard.
 * Completely separate from owner/guest Linas AI chat.
 */
export function LiveChatScreen({ onBack }: Props) {
  const inbox = useLiveChatInbox();
  const [selected, setSelected] = useState<LiveChatItem | null>(null);

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
