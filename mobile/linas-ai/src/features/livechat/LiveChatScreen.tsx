import { useEffect, useRef, useState } from 'react';

import { useI18n } from '../../i18n/LanguageContext';
import { useModuleNav } from '../nav/ModuleNavContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import { CommentsInbox } from './comments/CommentsInbox';
import { CommentThreadScreen } from './comments/CommentThreadScreen';
import { LiveChatSurfaceSwitch, type LiveChatSurface } from './comments/LiveChatSurfaceSwitch';
import type { CommentMediaItem, CommentPlatform } from './comments/commentsInboxTypes';
import { LiveChatInbox } from './LiveChatInbox';
import { LiveChatThread } from './LiveChatThread';
import type { LiveChatItem } from './liveChatTypes';
import { channelLabel, chatTitle } from './liveChatTypes';
import { useLiveChatInbox } from './useLiveChatInbox';

type Props = {
  initialOpen?: { userId: string; conversationId: string } | null;
};

export function LiveChatScreen({ initialOpen = null }: Props) {
  const { tr } = useI18n();
  const inbox = useLiveChatInbox();
  const nav = useModuleNav();
  const [surface, setSurface] = useState<LiveChatSurface>('chats');
  const [selected, setSelected] = useState<LiveChatItem | null>(null);
  const [commentPost, setCommentPost] = useState<{ platform: CommentPlatform; post: CommentMediaItem } | null>(null);
  const [deepLinkTried, setDeepLinkTried] = useState(false);
  const focusNonceSeen = useRef(nav.areaFocusNonce);

  useEffect(() => {
    if (nav.activeArea !== 'livechat') return;
    if (focusNonceSeen.current === nav.areaFocusNonce) return;
    focusNonceSeen.current = nav.areaFocusNonce;
    setSelected(null);
    setCommentPost(null);
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

  if (selected) {
    return (
      <ScreenChrome title={chatTitle(selected)} subtitle={channelLabel(selected)}>
        <LiveChatThread chat={selected} onChatUpdated={inbox.reloadQuiet} />
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
        <CommentThreadScreen platform={commentPost.platform} post={commentPost.post} />
      </ScreenChrome>
    );
  }

  return (
    <ScreenChrome title="Live Chat">
      <LiveChatSurfaceSwitch value={surface} onChange={setSurface} />
      {surface === 'comments' ? (
        <CommentsInbox onOpenThread={(platform, post) => setCommentPost({ platform, post })} />
      ) : (
        <LiveChatInbox inbox={inbox} onOpenChat={(chat) => setSelected(chat)} />
      )}
    </ScreenChrome>
  );
}
