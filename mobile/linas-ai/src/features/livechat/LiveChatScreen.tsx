import { useEffect, useRef, useState } from 'react';

import { useI18n } from '../../i18n/LanguageContext';
import { useModuleNav } from '../nav/ModuleNavContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import { CommentsInbox } from './comments/CommentsInbox';
import { CommentThreadScreen } from './comments/CommentThreadScreen';
import { LiveChatSurfaceSwitch, type LiveChatSurface } from './comments/LiveChatSurfaceSwitch';
import type { CommentMediaItem, CommentPlatform } from './comments/commentsInboxTypes';
import { InboxHumanHeaderButton } from './InboxHumanHeaderButton';
import { LiveChatInbox } from './LiveChatInbox';
import { LiveChatThread } from './LiveChatThread';
import type { LiveChatItem } from './liveChatTypes';
import { channelLabel, chatTitle } from './liveChatTypes';
import { sseEventMatchesChat, type LiveChatSseEvent } from './liveChatSseParse';
import { useLiveChatAccess } from './useLiveChatAccess';
import { useLiveChatEvents } from './useLiveChatEvents';
import { useLiveChatInbox } from './useLiveChatInbox';

type Props = {
  initialOpen?: { userId: string; conversationId: string } | null;
  active?: boolean;
};

export function LiveChatScreen({ initialOpen = null, active = true }: Props) {
  const { tr } = useI18n();
  const access = useLiveChatAccess();
  const inbox = useLiveChatInbox(access.canChats);
  const nav = useModuleNav();
  const [surface, setSurface] = useState<LiveChatSurface>('chats');
  const [selected, setSelected] = useState<LiveChatItem | null>(null);
  const [commentPost, setCommentPost] = useState<{ platform: CommentPlatform; post: CommentMediaItem } | null>(null);
  const [deepLinkTried, setDeepLinkTried] = useState(false);
  const [threadEvent, setThreadEvent] = useState<{ seq: number; event: LiveChatSseEvent } | null>(null);
  const [commentEvent, setCommentEvent] = useState<{ seq: number; event: LiveChatSseEvent } | null>(null);
  const [sseConnectedAt, setSseConnectedAt] = useState(0);
  const focusNonceSeen = useRef(nav.areaFocusNonce);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const canChatsRef = useRef(access.canChats);
  canChatsRef.current = access.canChats;
  const wasActive = useRef(active);

  const seenEventIds = useRef(new Set<string>());

  useLiveChatEvents({
    enabled: access.canChats || access.canComments,
    onEvent: (event) => {
      const eventId = String(event.data.event_id || '');
      if (eventId) {
        if (seenEventIds.current.has(eventId)) return;
        seenEventIds.current.add(eventId);
        if (seenEventIds.current.size > 400) {
          const first = seenEventIds.current.values().next().value;
          if (first) seenEventIds.current.delete(first);
        }
      }
      if (event.type === 'connected' || event.type === 'conversations') {
        if (canChatsRef.current) inbox.reloadFromEvent();
        if (event.type === 'connected') setSseConnectedAt(Date.now());
        return;
      }
      if (event.type === 'new_conversation') {
        if (canChatsRef.current) {
          inbox.applyNewMessage(event.data, selectedRef.current?.conversation_id ?? null);
        }
        return;
      }
      if (event.type === 'comment_update') {
        setCommentEvent({ seq: Date.now(), event });
        return;
      }
      if (event.type === 'new_message') {
        inbox.applyNewMessage(event.data, selectedRef.current?.conversation_id ?? null);
        if (sseEventMatchesChat(event.data, selectedRef.current)) {
          setThreadEvent({ seq: Date.now(), event });
        }
        return;
      }
      if (
        (event.type === 'message_updated' || event.type === 'message_status') &&
        sseEventMatchesChat(event.data, selectedRef.current)
      ) {
        setThreadEvent({ seq: Date.now(), event });
      }
    },
  });

  useEffect(() => {
    if (access.canChats && access.canComments) return;
    if (access.canComments) setSurface('comments');
    else setSurface('chats');
  }, [access.canChats, access.canComments]);

  useEffect(() => {
    if (nav.activeArea !== 'livechat' || !active) {
      wasActive.current = false;
      return;
    }
    const nonceChanged = focusNonceSeen.current !== nav.areaFocusNonce;
    const resumed = !wasActive.current;
    focusNonceSeen.current = nav.areaFocusNonce;
    wasActive.current = true;
    if (nonceChanged || resumed) inbox.catchUpIfStale();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keep the open thread; SSE patches the list
  }, [nav.areaFocusNonce, nav.activeArea, active]);

  useEffect(() => {
    if (!initialOpen || deepLinkTried || inbox.loading) {
      return;
    }
    const match = inbox.chats.find(
      (c) =>
        c.user_id === initialOpen.userId && c.conversation_id === initialOpen.conversationId,
    );
    if (match) {
      setSurface('chats');
      setSelected(match);
      setDeepLinkTried(true);
      return;
    }
    if (initialOpen.userId && initialOpen.conversationId) {
      setSurface('chats');
      setSelected({
        user_id: initialOpen.userId,
        conversation_id: initialOpen.conversationId,
        user_name: initialOpen.userId,
        status: 'waiting_human',
      });
      setDeepLinkTried(true);
    }
  }, [initialOpen, deepLinkTried, inbox.loading, inbox.chats]);

  const surfaces: LiveChatSurface[] = [];
  if (access.canChats) surfaces.push('chats');
  if (access.canComments) surfaces.push('comments');

  if (selected) {
    return (
      <ScreenChrome
        title={chatTitle(selected)}
        subtitle={channelLabel(selected)}
        onBack={() => setSelected(null)}
      >
        <LiveChatThread
          chat={selected}
          onChatUpdated={inbox.reloadQuiet}
          realtimeEvent={threadEvent}
          sseConnectedAt={sseConnectedAt}
        />
      </ScreenChrome>
    );
  }

  if (commentPost) {
    return (
      <ScreenChrome
        title={commentPost.post.caption.trim() || tr('liveCommentsUntitled')}
        subtitle={tr('liveCommentsThreadTitle')}
        onBack={() => setCommentPost(null)}
      >
        <CommentThreadScreen
          platform={commentPost.platform}
          post={commentPost.post}
          realtimeEvent={commentEvent}
          sseConnectedAt={sseConnectedAt}
        />
      </ScreenChrome>
    );
  }

  return (
    <ScreenChrome
      title="Live Chat"
      headerRight={
        access.canChats ? (
          <InboxHumanHeaderButton
            count={inbox.waitingCount}
            active={inbox.filter === 'waiting'}
            onPress={() => {
              setSurface('chats');
              inbox.setFilter(inbox.filter === 'waiting' ? 'all' : 'waiting');
            }}
          />
        ) : undefined
      }
    >
      <LiveChatSurfaceSwitch value={surface} onChange={setSurface} visible={surfaces} />
      {surface === 'comments' && access.canComments ? (
        <CommentsInbox
          allowedChannels={access.allowedChannels}
          realtimeEvent={commentEvent}
          onOpenThread={(platform, post) => setCommentPost({ platform, post })}
        />
      ) : (
        <LiveChatInbox
          inbox={inbox}
          allowedChannels={access.allowedChannels}
          onOpenChat={(chat) => setSelected(chat)}
        />
      )}
    </ScreenChrome>
  );
}
