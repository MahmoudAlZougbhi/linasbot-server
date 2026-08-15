import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Keyboard, type TextInput } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { useTheme } from '../../theme';
import { useBuyCreditsFlow } from '../billing/useBuyCreditsFlow';
import type { OwnerChatMode } from './ownerChatMode';
import { useModuleNavOptional } from '../nav/ModuleNavContext';
import { queueGuestDraft } from './pendingGuestDraft';
import { useChatIdentity } from './useChatIdentity';
import { useChatListScroll } from './useChatListScroll';
import { useChatSession } from './useChatSession';
import { useGuestChatSession } from './useGuestChatSession';
import { usePinnedChats } from './usePinnedChats';
import { appendVoiceTranscript, useVoiceDraft } from './useVoiceDraft';
import type { PendingFile } from './v2/pickAttachment';
import { useProposalEditMode } from './useProposalEditMode';
import { useStreamingTurn } from './v2/useStreamingTurn';

/** Owner/guest chat orchestration extracted from ChatScreen (line-limit split). */
export function useChatScreenController(
  isAuthenticated: boolean,
  onRequestLogin: () => void,
) {
  const { tr, language } = useI18n();
  const { colors } = useTheme();
  const nav = useModuleNavOptional();
  const owner = useChatSession(isAuthenticated);
  const guest = useGuestChatSession(!isAuthenticated);
  const [draft, setDraft] = useState('');
  const { userId, workspaceLabel } = useChatIdentity(isAuthenticated, setDraft);
  const { pinnedIds, togglePin } = usePinnedChats(userId);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [plusOpen, setPlusOpen] = useState(false);
  const [authGate, setAuthGate] = useState(false);
  const [hardLimit, setHardLimit] = useState(false);
  const [offline, setOffline] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const [ownerMode, setOwnerMode] = useState<OwnerChatMode>('chat');
  const promoteOwnerMode = useCallback((mode: OwnerChatMode) => {
    if (mode === 'work') setOwnerMode('work');
  }, []);
  const turn = useStreamingTurn(owner.conversationId, {
    onTerminal: (opts) => owner.syncAfterTurn(opts),
    onTitleUpdated: (title) => {
      if (owner.conversationId) {
        owner.applyConversationTitle(owner.conversationId, title, { onlyIfDefault: true });
      }
    },
    onOwnerModeHint: promoteOwnerMode,
  });
  const { reviseProposalId, setReviseProposalId, ownerSendWithMode } = useProposalEditMode(
    ownerMode,
    setOwnerMode,
    turn.send,
  );
  const imagePreviewByContent = useRef<Record<string, string[]>>({});
  const [choiceBusy, setChoiceBusy] = useState(false);
  const composerInputRef = useRef<TextInput>(null);
  const { listRef, stickToBottomRef, scrollToBottom, followBottomIfStuck, armOpenAtLatest } =
    useChatListScroll();
  const credits = useBuyCreditsFlow(() => turn.clearCreditsPaused());
  const voice = useVoiceDraft((text) => {
    setDraft((prev) => appendVoiceTranscript(prev, text));
    requestAnimationFrame(() => composerInputRef.current?.focus());
  });
  const authVoice = isAuthenticated ? voice : null;

  const startNewChat = useCallback(() => {
    if (!isAuthenticated) return;
    Keyboard.dismiss();
    composerInputRef.current?.blur();
    stickToBottomRef.current = true;
    setOwnerMode('chat');
    setReviseProposalId(null);
    if (turn.streaming) turn.stop();
    void owner.newChat();
  }, [isAuthenticated, owner, setReviseProposalId, stickToBottomRef, turn]);

  useEffect(() => {
    if (guest.gated) {
      setHardLimit(true);
      setAuthGate(true);
    }
  }, [guest.gated]);

  const archivedIds = useMemo(
    () => owner.history.filter((h) => h.archived).map((h) => h.id),
    [owner.history],
  );

  const loading = isAuthenticated ? owner.loading : guest.loading;
  const messages = isAuthenticated ? owner.messages : guest.messages;
  const sessionReady = isAuthenticated && !owner.loading && Boolean(owner.conversationId);
  const sending = isAuthenticated ? turn.streaming || owner.loading : guest.sending;
  const error = isAuthenticated ? owner.error : guest.error;
  const listKey = isAuthenticated ? owner.conversationId || 'owner' : guest.guestId || 'guest';
  const hasUserMessage = messages.some((m) => m.role === 'user');
  const showModeToggle = isAuthenticated && !hasUserMessage && !turn.liveText && !turn.streaming;

  useEffect(() => {
    if (loading) return;
    armOpenAtLatest({ pinToLatest: hasUserMessage });
  }, [armOpenAtLatest, hasUserMessage, loading, listKey]);

  useEffect(() => {
    followBottomIfStuck(false);
  }, [
    messages.length,
    turn.thinking,
    turn.liveText,
    turn.statusRows.length,
    turn.cards.length,
    turn.choices.length,
    followBottomIfStuck,
  ]);

  const openAuthPreservingDraft = useCallback((hard = false) => {
    queueGuestDraft(draft);
    setHardLimit(hard);
    setAuthGate(true);
  }, [draft]);

  const goToLoginPreservingDraft = useCallback(() => {
    Keyboard.dismiss();
    queueGuestDraft(draft);
    onRequestLogin();
  }, [draft, onRequestLogin]);

  return {
    tr,
    language,
    colors,
    nav,
    owner,
    guest,
    draft,
    setDraft,
    workspaceLabel,
    pinnedIds,
    togglePin,
    drawerOpen,
    setDrawerOpen,
    plusOpen,
    setPlusOpen,
    authGate,
    setAuthGate,
    hardLimit,
    setHardLimit,
    offline,
    setOffline,
    pendingFiles,
    setPendingFiles,
    ownerMode,
    setOwnerMode,
    turn,
    reviseProposalId,
    setReviseProposalId,
    ownerSendWithMode,
    imagePreviewByContent,
    choiceBusy,
    setChoiceBusy,
    composerInputRef,
    listRef,
    stickToBottomRef,
    scrollToBottom,
    followBottomIfStuck,
    armOpenAtLatest,
    credits,
    voice,
    authVoice,
    startNewChat,
    openAuthPreservingDraft,
    goToLoginPreservingDraft,
    archivedIds,
    loading,
    messages,
    sessionReady,
    sending,
    error,
    listKey,
    hasUserMessage,
    showModeToggle,
  };
}
