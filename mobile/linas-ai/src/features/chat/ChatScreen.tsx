import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  TextInput,
  View,
} from 'react-native';

import { GradientBackground } from '../../components/GradientBackground';
import { useI18n } from '../../i18n/LanguageContext';
import { useTheme } from '../../theme';
import type { ControlArea } from '../control/controlAreas';
import type { CmProposalReview } from '../cm/cmProposalReview';
import { ChatComposer } from './ChatComposer';
import { ChatHeader } from './ChatHeader';
import { ChatMessageList } from './ChatMessageList';
import { ChatModeToggle } from './ChatModeToggle';
import { ChatScreenOverlays } from './ChatScreenOverlays';
import { chatScreenStyles as styles } from './chatScreenStyles';
import { ChatStatusBanners } from './ChatStatusBanners';
import type { OwnerChatMode } from './ownerChatMode';
import { resolveOwnerModeForOutgoing } from './ownerChatMode';
import { PendingAttachmentsStrip } from './PendingAttachmentsStrip';
import { queueGuestDraft } from './pendingGuestDraft';
import { buildApproveSendOpts, buildDiscardSendOpts } from './proposalBarActions';
import { sendChatMessage } from './sendChatMessage';
import { chatErrorLabelKey, retryAssistantMessage } from './chatRetryHandlers';
import { useChatIdentity } from './useChatIdentity';
import { useChatListScroll } from './useChatListScroll';
import { useChatSession } from './useChatSession';
import { useGuestChatSession } from './useGuestChatSession';
import { usePendingChatNavHandoff } from './usePendingChatNavHandoff';
import { usePinnedChats } from './usePinnedChats';
import { appendVoiceTranscript, useVoiceDraft } from './useVoiceDraft';
import { ChoiceChips } from './v2/ChoiceChips';
import type { PendingFile } from './v2/pickAttachment';
import { useSetupHandoff } from './useSetupHandoff';
import { useProposalEditMode } from './useProposalEditMode';
import { useStreamingTurn } from './v2/useStreamingTurn';

type Props = {
  isAuthenticated: boolean;
  onOpenArea: (area: ControlArea) => void;
  onOpenCmReview?: (review: CmProposalReview) => void;
  onRequestLogin: () => void;
  onRequestRegister: () => void;
};
export function ChatScreen({
  isAuthenticated,
  onOpenArea,
  onOpenCmReview,
  onRequestLogin,
  onRequestRegister,
}: Props) {
  const { tr, language } = useI18n();
  const { colors } = useTheme();
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
  const promoteOwnerMode = useCallback((mode: OwnerChatMode) => { if (mode === 'work') setOwnerMode('work'); }, []);
  const turn = useStreamingTurn(owner.conversationId, {
    onTerminal: (opts) => owner.syncAfterTurn(opts),
    onTitleUpdated: (title) => {
      if (owner.conversationId) {
        owner.applyConversationTitle(owner.conversationId, title, { onlyIfDefault: true });
      }
    },
    onOwnerModeHint: promoteOwnerMode,
  });
  const { reviseProposalId, setReviseProposalId, ownerSendWithMode } = useProposalEditMode(ownerMode, setOwnerMode, turn.send);
  const imagePreviewByContent = useRef<Record<string, string[]>>({});
  const [choiceBusy, setChoiceBusy] = useState(false);
  const composerInputRef = useRef<TextInput>(null);
  const { listRef, stickToBottomRef, scrollToBottom, followBottomIfStuck, armOpenAtLatest } = useChatListScroll();
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
  }, [isAuthenticated, owner, stickToBottomRef, turn]);

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
  // Greeting-seeded chats: show Chat|Work until first user message.
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

  function openAuthPreservingDraft(hard = false) {
    queueGuestDraft(draft);
    setHardLimit(hard); setAuthGate(true);
  }
  function goToLoginPreservingDraft() {
    Keyboard.dismiss();
    queueGuestDraft(draft);
    onRequestLogin();
  }

  useSetupHandoff({
    isAuthenticated,
    loading: owner.loading,
    streaming: turn.streaming,
    setDraft,
    setOwnerMode,
    send: (text, mode) => {
      stickToBottomRef.current = true;
      void turn.send(text, { owner_mode: mode });
    },
  });

  usePendingChatNavHandoff({
    isAuthenticated,
    owner,
    turn,
    setOwnerMode,
    stickToBottom: () => {
      stickToBottomRef.current = true;
    },
    afterOpen: () => armOpenAtLatest(),
  });

  return (
    <GradientBackground>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={0}
      >
        <View style={styles.flex}>
        {showModeToggle ? <ChatModeToggle mode={ownerMode} onChange={setOwnerMode} /> : null}

        <ChatStatusBanners
          offline={offline}
          errorLabel={error ? tr(chatErrorLabelKey(error)) : null}
          voiceError={voice.voiceError}
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
            followBottomIfStuck={followBottomIfStuck}
            imagePreviewByContent={imagePreviewByContent}
            thinking={turn.thinking || (!isAuthenticated && guest.sending)}
            thinkingLabel={tr('chatThinking')}
            statusRows={turn.statusRows}
            liveText={turn.liveText}
            cards={turn.cards}
            proposedPatch={isAuthenticated ? owner.proposedPatch : null}
            hasMore={isAuthenticated ? owner.hasMore : false}
            loadingMore={isAuthenticated ? owner.loadingMore : false}
            onLoadOlder={() => {
              if (isAuthenticated) void owner.loadOlder();
            }}
            onRetryAssistant={(content) =>
              retryAssistantMessage({
                isAuthenticated,
                streaming: turn.streaming,
                guestSending: guest.sending,
                guestGated: guest.gated,
                content,
                ownerSend: (text) => void ownerSendWithMode(text),
                guestSend: (text) => void guest.send(text),
                openAuth: () => openAuthPreservingDraft(true),
                scrollToBottom,
              })
            }
            onApproveDraft={(token, approveOpts) => {
              setReviseProposalId(null);
              void ownerSendWithMode('', buildApproveSendOpts(token, approveOpts));
            }}
            onDiscardProposal={(token) => {
              owner.setProposedPatch(null);
              owner.setPendingConfirm(null);
              setReviseProposalId(null);
              const d = buildDiscardSendOpts(token);
              if (d) void ownerSendWithMode('', d);
            }}
            onEditProposal={(id) => {
              setReviseProposalId(id);
              composerInputRef.current?.focus();
            }}
            onOpenCm={(r) => (r && onOpenCmReview ? onOpenCmReview(r) : onOpenArea('cm'))}
            onGuestPrompt={(prompt) => {
              if (guest.gated) {
                openAuthPreservingDraft(true);
                return;
              }
              scrollToBottom();
              void guest.send(prompt);
            }}
            showOwnerWelcomeChips={
              isAuthenticated && !hasUserMessage && !turn.liveText && !turn.streaming
            }
            onOwnerWelcomeChip={(chip) => {
              const mode = resolveOwnerModeForOutgoing(chip.mode, chip.prompt);
              setOwnerMode(mode);
              scrollToBottom();
              void turn.send(chip.prompt, { owner_mode: mode, reply_language: language });
            }}
            seedTypewriterMessageId={isAuthenticated ? owner.seedTypewriterMessageId : null}
            onSeedTypewriterDone={owner.clearSeedTypewriter}
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
          sending={sending || (!isAuthenticated && guest.gated) || (isAuthenticated && !sessionReady)}
          canSendWithAttachment={pendingFiles.length > 0}
          voiceState={authVoice?.voiceState ?? 'idle'}
          elapsedMs={authVoice?.elapsedMs ?? 0}
          metering={authVoice?.metering ?? null}
          inputRef={composerInputRef}
          showPlus={isAuthenticated}
          showMic={isAuthenticated}
          showModelChip={isAuthenticated}
          ownerMode={ownerMode}
          onOwnerModeChange={setOwnerMode}
          editChipActive={Boolean(reviseProposalId)}
          onClearEditChip={() => setReviseProposalId(null)}
          onPlus={() => setPlusOpen(true)}
          onToggleVoice={() => void voice.toggleVoice()}
          onResumeVoice={() => void voice.resumeVoice()}
          onConfirmVoice={() => void voice.confirmVoice()}
          onDiscardVoice={() => void voice.discardVoice()}
          onStop={turn.streaming ? () => turn.stop() : undefined}
          onSend={() =>
            void sendChatMessage({
              isAuthenticated,
              draft,
              setDraft,
              pendingFiles,
              setPendingFiles,
              voiceState: voice.voiceState,
              conversationId: owner.conversationId,
              guestGated: guest.gated,
              guestSend: guest.send,
              ownerSend: ownerSendWithMode,
              appendOptimisticUser: owner.appendOptimisticUser,
              removeOptimisticUser: owner.removeOptimisticUser,
              autoTitleFromOutgoing: owner.autoTitleFromOutgoing,
              openAuthPreservingDraft,
              setOffline,
              setSendError: (v) => (isAuthenticated ? owner.setError(v) : guest.setError(v)),
              scrollToBottom,
              imagePreviewByContent,
            })
          }
        />
        </View>
      </KeyboardAvoidingView>
      <ChatHeader
        onOpenMenu={() => {
          Keyboard.dismiss();
          setDrawerOpen(true);
        }}
      />

      <ChatScreenOverlays
        drawerOpen={drawerOpen}
        onCloseDrawer={() => setDrawerOpen(false)}
        isAuthenticated={isAuthenticated}
        activeArea="chat"
        history={owner.history}
        archivedIds={archivedIds}
        pinnedIds={pinnedIds}
        activeId={owner.conversationId}
        workspaceLabel={workspaceLabel}
        onOpenArea={onOpenArea}
        onNewChat={() => { setDrawerOpen(false); startNewChat(); }}
        onOpenChat={(id) => {
          stickToBottomRef.current = true;
          void owner.openConversation(id).then(() => armOpenAtLatest());
        }}
        onTogglePin={(id) => void togglePin(id)}
        onArchive={(id) => void owner.setArchived(id, true)}
        onUnarchive={(id) => void owner.setArchived(id, false)}
        onRename={(id, title) => void owner.renameConversation(id, title)}
        onDelete={(id) => void owner.deleteConversation(id)}
        onLogin={goToLoginPreservingDraft}
        onRegister={onRequestRegister}
        plusOpen={plusOpen}
        onClosePlus={() => setPlusOpen(false)}
        pendingFiles={pendingFiles}
        setPendingFiles={setPendingFiles}
        authGate={authGate}
        hardLimit={hardLimit}
        guestGated={guest.gated}
        gateText={guest.gateText}
        onCloseAuth={() => { setAuthGate(false); setHardLimit(false); }}
        onRequestLogin={onRequestLogin}
        onRequestRegister={onRequestRegister}
      />
    </GradientBackground>
  );
}
