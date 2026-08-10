import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  TextInput,
  View,
} from 'react-native';

import { GradientBackground } from '../../components/GradientBackground';
import { tokenStore } from '../../auth/tokenStore';
import { useI18n } from '../../i18n/LanguageContext';
import { useTheme } from '../../theme';
import type { ControlArea } from '../control/controlAreas';
import { ChatComposer } from './ChatComposer';
import { ChatHeader } from './ChatHeader';
import { ChatMessageList } from './ChatMessageList';
import { ChatModeToggle } from './ChatModeToggle';
import { ChatScreenOverlays } from './ChatScreenOverlays';
import { chatScreenStyles as styles } from './chatScreenStyles';
import { ChatStatusBanners } from './ChatStatusBanners';
import { ChatWorkspaceChip } from './ChatWorkspaceChip';
import { GuestBanner } from './GuestBanner';
import type { OwnerChatMode } from './ownerChatMode';
import { PendingAttachmentsStrip } from './PendingAttachmentsStrip';
import {
  clearPendingGuestDraft,
  loadPendingGuestDraft,
  savePendingGuestDraft,
} from './pendingGuestDraft';
import { sendChatMessage } from './sendChatMessage';
import { useChatSession } from './useChatSession';
import { useGuestChatSession } from './useGuestChatSession';
import { usePinnedChats } from './usePinnedChats';
import { useVoiceDraft } from './useVoiceDraft';
import { ChoiceChips } from './v2/ChoiceChips';
import type { PendingFile } from './v2/pickAttachment';
import { useStreamingTurn } from './v2/useStreamingTurn';

type Props = {
  isAuthenticated: boolean;
  isPlatformOwner: boolean;
  onOpenArea: (area: ControlArea) => void;
  onRequestLogin: () => void;
  onRequestRegister: () => void;
};

export function ChatScreen({
  isAuthenticated,
  onOpenArea,
  onRequestLogin,
  onRequestRegister,
}: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();
  const owner = useChatSession(isAuthenticated);
  const guest = useGuestChatSession(!isAuthenticated);
  const turn = useStreamingTurn(owner.conversationId, {
    onTerminal: () => owner.syncAfterTurn(),
    onTitleUpdated: (title) => {
      if (owner.conversationId) {
        owner.applyConversationTitle(owner.conversationId, title, { onlyIfDefault: true });
      }
    },
  });
  const [userId, setUserId] = useState<string | null>(null);
  const [workspaceLabel, setWorkspaceLabel] = useState<string | null>(null);
  const { pinnedIds, togglePin } = usePinnedChats(userId);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [plusOpen, setPlusOpen] = useState(false);
  const [authGate, setAuthGate] = useState(false);
  const [hardLimit, setHardLimit] = useState(false);
  const [offline, setOffline] = useState(false);
  const [draft, setDraft] = useState('');
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const [ownerMode, setOwnerMode] = useState<OwnerChatMode>('chat');
  const imagePreviewByContent = useRef<Record<string, string[]>>({});
  const [choiceBusy, setChoiceBusy] = useState(false);
  const composerInputRef = useRef<TextInput>(null);
  const listRef = useRef<FlatList>(null);
  const stickToBottomRef = useRef(true);
  const { voiceState, voiceError, toggleVoice, metering } = useVoiceDraft((text) => {
    setDraft((prev) => (prev ? `${prev} ${text}` : text));
    requestAnimationFrame(() => composerInputRef.current?.focus());
  });

  const scrollToBottom = useCallback((animated = true) => {
    stickToBottomRef.current = true;
    requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated }));
  }, []);

  const armOpenAtLatest = useCallback(() => {
    stickToBottomRef.current = true;
    const run = (animated: boolean) => listRef.current?.scrollToEnd({ animated });
    requestAnimationFrame(() => run(false));
    setTimeout(() => run(false), 50);
    setTimeout(() => run(false), 180);
  }, []);

  const startNewChat = useCallback(() => {
    if (!isAuthenticated) return;
    stickToBottomRef.current = true;
    setOwnerMode('chat');
    if (turn.streaming) turn.stop();
    void owner.newChat();
  }, [isAuthenticated, owner, turn]);

  useEffect(() => {
    if (!isAuthenticated) {
      setUserId(null);
      setWorkspaceLabel(null);
      return;
    }
    void tokenStore.getUser().then((u) => {
      setUserId(u?.id ?? null);
      setWorkspaceLabel(u?.tenantId || u?.tenant_id || u?.email || null);
    });
    void loadPendingGuestDraft().then((pending) => {
      if (pending?.text) {
        setDraft(pending.text);
        void clearPendingGuestDraft();
      }
    });
  }, [isAuthenticated]);

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
  const sending = isAuthenticated ? turn.streaming : guest.sending;
  const error = isAuthenticated ? owner.error : guest.error;
  const listKey = isAuthenticated ? owner.conversationId || 'owner' : 'guest';
  // New owner chats always seed an assistant greeting — gate on first user message, not empty list.
  const hasUserMessage = messages.some((m) => m.role === 'user');
  const showModeToggle =
    isAuthenticated && !hasUserMessage && !turn.liveText && !turn.streaming;

  useEffect(() => {
    if (loading) return;
    armOpenAtLatest();
  }, [armOpenAtLatest, loading, listKey]);

  useEffect(() => {
    if (!stickToBottomRef.current) return;
    scrollToBottom(false);
  }, [
    messages.length,
    turn.liveText,
    turn.statusRows.length,
    turn.cards.length,
    turn.choices.length,
    scrollToBottom,
  ]);

  function openAuthPreservingDraft(hard = false) {
    void savePendingGuestDraft({ text: draft, createdAt: Date.now() });
    setHardLimit(hard);
    setAuthGate(true);
  }

  const ownerSendWithMode = useCallback(
    (
      text: string,
      opts?: {
        attachment_ids?: string[];
        choice_id?: string;
        choice_set_id?: string;
        confirm_tool?: string | null;
      },
    ) => turn.send(text, { ...opts, owner_mode: ownerMode }),
    [ownerMode, turn],
  );

  // ChatGPT-like open: keep chat chrome up — no second full-screen spinner after boot.
  return (
    <GradientBackground>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={0}
      >
        <ChatHeader
          isAuthenticated={isAuthenticated}
          workspaceLabel={null}
          onOpenMenu={() => {
            Keyboard.dismiss();
            setDrawerOpen(true);
          }}
          onNewChat={startNewChat}
          onSignIn={() => openAuthPreservingDraft(false)}
        />

        {showModeToggle ? <ChatModeToggle mode={ownerMode} onChange={setOwnerMode} /> : null}
        {isAuthenticated && workspaceLabel ? <ChatWorkspaceChip label={workspaceLabel} /> : null}

        {!isAuthenticated ? (
          <GuestBanner
            remaining={guest.questionsRemaining}
            max={guest.maxQuestions}
            gated={guest.gated}
            onLogin={() => openAuthPreservingDraft(true)}
          />
        ) : null}

        <ChatStatusBanners
          offline={offline}
          errorLabel={
            error
              ? tr(
                  error === 'retry' || error === 'guestWordLimit' || error === 'guestModelUnavailable'
                    ? error
                    : 'messageFailed',
                )
              : null
          }
          voiceError={voiceError}
          onRetry={() => {
            setOffline(false);
            if (!isAuthenticated) {
              guest.setError(null);
              void guest.bootstrap();
              return;
            }
            const err = owner.error;
            owner.setError(null);
            if (err === 'messageFailed') return;
            void owner.bootstrap();
          }}
        />

        {loading ? (
          <View style={styles.center} accessibilityLabel="Loading conversation">
            <ActivityIndicator color={colors.accent} />
          </View>
        ) : (
          <ChatMessageList
            listRef={listRef}
            listKey={listKey}
            messages={messages}
            isAuthenticated={isAuthenticated}
            stickToBottomRef={stickToBottomRef}
            scrollToBottom={scrollToBottom}
            imagePreviewByContent={imagePreviewByContent}
            statusRows={turn.statusRows}
            liveText={turn.liveText}
            cards={turn.cards}
            proposedPatch={isAuthenticated ? owner.proposedPatch : null}
            hasMore={isAuthenticated ? owner.hasMore : false}
            loadingMore={isAuthenticated ? owner.loadingMore : false}
            onLoadOlder={() => {
              if (isAuthenticated) void owner.loadOlder();
            }}
            onRetryAssistant={(content) => {
              if (turn.streaming) return;
              void ownerSendWithMode(content);
            }}
            onApproveDraft={(token) => void ownerSendWithMode('', { confirm_tool: token })}
            onDiscardProposal={() => {
              owner.setProposedPatch(null);
              owner.setPendingConfirm(null);
            }}
            onOpenCm={() => onOpenArea('cm')}
            onGuestPrompt={(prompt) => {
              if (guest.gated) {
                openAuthPreservingDraft(true);
                return;
              }
              scrollToBottom();
              void guest.send(prompt);
            }}
          />
        )}

        {isAuthenticated ? (
          <ChoiceChips
            choices={turn.choices}
            disabled={choiceBusy || turn.streaming}
            onSelect={(c) => {
              if (!turn.choiceSetId || choiceBusy) return;
              setChoiceBusy(true);
              scrollToBottom();
              void ownerSendWithMode(c.label, {
                choice_id: c.id,
                choice_set_id: turn.choiceSetId,
              }).finally(() => setChoiceBusy(false));
            }}
          />
        ) : null}

        <PendingAttachmentsStrip
          files={pendingFiles}
          onRemove={(id) => setPendingFiles((prev) => prev.filter((f) => f.id !== id))}
        />

        <ChatComposer
          draft={draft}
          onChangeDraft={setDraft}
          sending={sending || (!isAuthenticated && guest.gated)}
          canSendWithAttachment={pendingFiles.length > 0}
          voiceState={isAuthenticated ? voiceState : 'idle'}
          metering={isAuthenticated ? metering : null}
          inputRef={composerInputRef}
          autoFocus
          showPlus={isAuthenticated}
          showMic={isAuthenticated}
          showModelChip={isAuthenticated}
          ownerMode={ownerMode}
          onPlus={() => setPlusOpen(true)}
          onToggleVoice={() => void toggleVoice()}
          onStop={turn.streaming ? () => turn.stop() : undefined}
          onSend={() =>
            void sendChatMessage({
              isAuthenticated,
              draft,
              setDraft,
              pendingFiles,
              setPendingFiles,
              voiceState,
              conversationId: owner.conversationId,
              guestGated: guest.gated,
              guestQuestionsRemaining: guest.questionsRemaining,
              guestSend: guest.send,
              ownerSend: ownerSendWithMode,
              appendOptimisticUser: owner.appendOptimisticUser,
              removeOptimisticUser: owner.removeOptimisticUser,
              autoTitleFromOutgoing: owner.autoTitleFromOutgoing,
              openAuthPreservingDraft,
              setOffline,
              setSendError: (v) => {
                if (isAuthenticated) owner.setError(v);
                else guest.setError(v);
              },
              scrollToBottom,
              imagePreviewByContent,
            })
          }
        />
      </KeyboardAvoidingView>

      <ChatScreenOverlays
        drawerOpen={drawerOpen}
        onCloseDrawer={() => setDrawerOpen(false)}
        isAuthenticated={isAuthenticated}
        history={owner.history}
        archivedIds={archivedIds}
        pinnedIds={pinnedIds}
        activeId={owner.conversationId}
        workspaceLabel={workspaceLabel}
        onOpenArea={onOpenArea}
        onNewChat={() => {
          setDrawerOpen(false);
          startNewChat();
        }}
        onOpenChat={(id) => {
          stickToBottomRef.current = true;
          void owner.openConversation(id).then(() => armOpenAtLatest());
        }}
        onTogglePin={(id) => void togglePin(id)}
        onArchive={(id) => void owner.setArchived(id, true)}
        onUnarchive={(id) => void owner.setArchived(id, false)}
        onRename={(id, title) => void owner.renameConversation(id, title)}
        onDelete={(id) => void owner.deleteConversation(id)}
        onLogin={() => openAuthPreservingDraft(false)}
        onRegister={onRequestRegister}
        plusOpen={plusOpen}
        onClosePlus={() => setPlusOpen(false)}
        pendingFiles={pendingFiles}
        setPendingFiles={setPendingFiles}
        authGate={authGate}
        hardLimit={hardLimit}
        guestGated={guest.gated}
        gateText={guest.gateText}
        onCloseAuth={() => {
          setAuthGate(false);
          setHardLimit(false);
        }}
        onRequestLogin={onRequestLogin}
        onRequestRegister={onRequestRegister}
      />
    </GradientBackground>
  );
}
