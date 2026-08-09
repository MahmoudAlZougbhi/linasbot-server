import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  TextInput,
  View,
} from 'react-native';

import { GradientBackground } from '../../components/GradientBackground';
import { tokenStore } from '../../auth/tokenStore';
import { useI18n } from '../../i18n/LanguageContext';
import { useTheme } from '../../theme';
import { AuthGateModal } from '../auth/AuthGateModal';
import type { ControlArea } from '../control/controlAreas';
import { NavDrawer } from '../nav/NavDrawer';
import { ChatComposer } from './ChatComposer';
import { ChatHeader } from './ChatHeader';
import { ChatMessageList } from './ChatMessageList';
import { chatScreenStyles as styles } from './chatScreenStyles';
import { ChatStatusBanners } from './ChatStatusBanners';
import { ComposerPlusSheet, type PlusAction } from './ComposerPlusSheet';
import { GuestBanner } from './GuestBanner';
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
import {
  MAX_IMAGES,
  pickDocumentAttachment,
  pickImageAttachments,
  type PendingFile,
} from './v2/pickAttachment';
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

  /** Open / switch chat: always land on latest after layout (RN scrollToEnd is flaky on mount). */
  const armOpenAtLatest = useCallback(() => {
    stickToBottomRef.current = true;
    const run = (animated: boolean) => listRef.current?.scrollToEnd({ animated });
    requestAnimationFrame(() => run(false));
    setTimeout(() => run(false), 50);
    setTimeout(() => run(false), 180);
  }, []);

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

  async function handlePlus(action: PlusAction) {
    if (!isAuthenticated) return;
    if (action === 'add_cm' || action === 'review_setup') {
      onOpenArea('cm');
      return;
    }
    if (action === 'check_usage') {
      onOpenArea('usage');
      return;
    }
    if (action === 'attach_image') {
      const picked = await pickImageAttachments(pendingFiles.length);
      if (!picked.length) return;
      setPendingFiles((prev) => [...prev, ...picked].slice(0, MAX_IMAGES));
      return;
    }
    if (action === 'attach_document') {
      if (pendingFiles.length >= MAX_IMAGES) return;
      const doc = await pickDocumentAttachment();
      if (doc) setPendingFiles((prev) => [...prev, doc].slice(0, MAX_IMAGES));
    }
  }

  function openAuthPreservingDraft(hard = false) {
    void savePendingGuestDraft({ text: draft, createdAt: Date.now() });
    setHardLimit(hard);
    setAuthGate(true);
  }

  if (loading) {
    return (
      <GradientBackground>
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent} />
        </View>
      </GradientBackground>
    );
  }

  return (
    <GradientBackground>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={0}
      >
        <ChatHeader
          isAuthenticated={isAuthenticated}
          workspaceLabel={workspaceLabel}
          onOpenMenu={() => setDrawerOpen(true)}
          onSignIn={() => openAuthPreservingDraft(false)}
          onNewChat={() => {
            stickToBottomRef.current = true;
            void owner.newChat();
          }}
        />

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
            if (isAuthenticated) { owner.setError(null); void owner.bootstrap(); }
            else { guest.setError(null); void guest.bootstrap(); }
          }}
        />

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
          onRetryAssistant={(content) => void turn.send(content)}
          onApproveDraft={(token) => void turn.send('', { confirm_tool: token })}
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

        {isAuthenticated ? (
          <ChoiceChips
            choices={turn.choices}
            disabled={choiceBusy || turn.streaming}
            onSelect={(c) => {
              if (!turn.choiceSetId || choiceBusy) return;
              setChoiceBusy(true);
              scrollToBottom();
              void turn
                .send(c.label, { choice_id: c.id, choice_set_id: turn.choiceSetId })
                .finally(() => setChoiceBusy(false));
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
              ownerSend: turn.send,
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

      <NavDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        isAuthenticated={isAuthenticated}
        showUsers={isAuthenticated}
        history={owner.history}
        archivedIds={archivedIds}
        pinnedIds={pinnedIds}
        activeId={owner.conversationId}
        workspaceLabel={workspaceLabel}
        onOpenArea={onOpenArea}
        onNewChat={() => {
          if (isAuthenticated) void owner.newChat();
          else setDrawerOpen(false);
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
      />

      {isAuthenticated ? (
        <ComposerPlusSheet open={plusOpen} onClose={() => setPlusOpen(false)} onAction={(a) => void handlePlus(a)} />
      ) : null}

      <AuthGateModal
        visible={authGate}
        hardLimit={hardLimit || guest.gated}
        reason={guest.gateText ?? undefined}
        onClose={() => {
          setAuthGate(false);
          setHardLimit(false);
        }}
        onLogin={() => {
          setAuthGate(false);
          onRequestLogin();
        }}
        onRegister={() => {
          setAuthGate(false);
          onRequestRegister();
        }}
      />
    </GradientBackground>
  );
}
