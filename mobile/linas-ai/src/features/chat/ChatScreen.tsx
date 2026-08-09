import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  Text,
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
import { ChatBubble } from './ChatBubble';
import { ChatComposer } from './ChatComposer';
import { ChatHeader } from './ChatHeader';
import { chatScreenStyles as styles } from './chatScreenStyles';
import { ComposerPlusSheet, type PlusAction } from './ComposerPlusSheet';
import { GuestBanner } from './GuestBanner';
import { GuestEmptyState } from './GuestEmptyState';
import { PendingAttachmentsStrip } from './PendingAttachmentsStrip';
import {
  clearPendingGuestDraft,
  loadPendingGuestDraft,
  savePendingGuestDraft,
} from './pendingGuestDraft';
import { useChatSession } from './useChatSession';
import { useGuestChatSession } from './useGuestChatSession';
import { usePinnedChats } from './usePinnedChats';
import { useVoiceDraft } from './useVoiceDraft';
import { ActivityCard } from './v2/ActivityCard';
import { ChoiceChips } from './v2/ChoiceChips';
import {
  isImageMime,
  MAX_IMAGES,
  pickDocumentAttachment,
  pickImageAttachments,
  type PendingFile,
} from './v2/pickAttachment';
import { uploadOwnerAttachment } from './v2/useOwnerStream';
import { useStreamingTurn } from './v2/useStreamingTurn';

type Props = {
  isAuthenticated: boolean;
  isPlatformOwner: boolean;
  onOpenArea: (area: ControlArea) => void;
  onLogout: () => void;
  onRequestLogin: () => void;
  onRequestRegister: () => void;
};

export function ChatScreen({
  isAuthenticated,
  onOpenArea,
  onLogout,
  onRequestLogin,
  onRequestRegister,
}: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();
  const owner = useChatSession(isAuthenticated);
  const guest = useGuestChatSession(!isAuthenticated);
  const turn = useStreamingTurn(owner.conversationId, owner.bootstrap);
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
  /** Rematch local thumbs onto server messages after stream bootstrap. */
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
    requestAnimationFrame(() => {
      listRef.current?.scrollToEnd({ animated });
    });
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
    void savePendingGuestDraft({
      text: draft,
      createdAt: Date.now(),
    });
    setHardLimit(hard);
    setAuthGate(true);
  }

  async function handleSend() {
    if (!isAuthenticated) {
      if (guest.gated || guest.questionsRemaining <= 0) {
        openAuthPreservingDraft(true);
        return;
      }
      const text = draft.trim();
      if (!text) return;
      setDraft('');
      scrollToBottom();
      const result = await guest.send(text);
      if (result === 'skipped' || result === 'rejected' || result === 'error') {
        setDraft(text);
        if (result === 'error') setOffline(true);
        return;
      }
      return;
    }

    if (voiceState === 'recording' || voiceState === 'transcribing') return;
    if (!owner.conversationId) {
      setOffline(true);
      return;
    }

    const text = draft.trim();
    const files = pendingFiles;
    if (!text && !files.length) return;

    const outgoing =
      text ||
      (files.length > 1 ? 'Please analyze these attachments.' : 'Please analyze this attachment.');
    setDraft('');
    setPendingFiles([]);
    scrollToBottom();

    let attachmentIds: string[] | undefined;
    if (files.length) {
      try {
        const uploaded = await Promise.all(files.map((f) => uploadOwnerAttachment(f)));
        attachmentIds = uploaded.map((u) => u.attachment_id);
      } catch {
        setDraft(text);
        setPendingFiles(files);
        setOffline(true);
        return;
      }
    }

    const imageUris = files.filter((f) => isImageMime(f.mimeType)).map((f) => f.uri);
    if (imageUris.length) {
      imagePreviewByContent.current[outgoing] = imageUris;
    }

    const optimisticId = owner.appendOptimisticUser(
      outgoing,
      imageUris.length ? imageUris : undefined,
    );
    const result = await turn.send(outgoing, { attachment_ids: attachmentIds });
    if (result === 'skipped' || result === 'error') {
      owner.removeOptimisticUser(optimisticId);
      setDraft(text);
      setPendingFiles(files);
      if (result === 'error') setOffline(true);
      return;
    }
    if (result === 'cancelled') {
      // Keep optimistic user + whatever bootstrap hydrates; do not restore draft.
      return;
    }
    scrollToBottom();
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
          onNewChat={() => void owner.newChat()}
        />

        {!isAuthenticated ? (
          <GuestBanner
            remaining={guest.questionsRemaining}
            max={guest.maxQuestions}
            gated={guest.gated}
            onLogin={() => openAuthPreservingDraft(true)}
          />
        ) : null}

        {offline ? (
          <Text style={[styles.error, { color: colors.warning }]}>
            Offline — your draft is preserved. Retry when connected.
          </Text>
        ) : null}

        {error ? (
          <Pressable
            onPress={() => {
              setOffline(false);
              void (isAuthenticated ? owner.bootstrap() : guest.bootstrap());
            }}
          >
            <Text style={styles.error}>
              {tr(
                error === 'retry' || error === 'guestWordLimit' || error === 'guestModelUnavailable'
                  ? error
                  : 'messageFailed',
              )}{' '}
              · Tap to retry
            </Text>
          </Pressable>
        ) : null}
        {voiceError ? <Text style={styles.error}>{voiceError}</Text> : null}

        <FlatList
          ref={listRef}
          style={styles.flex}
          data={messages}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.list}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="interactive"
          onContentSizeChange={() => {
            if (stickToBottomRef.current) scrollToBottom(false);
          }}
          onScrollBeginDrag={() => {
            stickToBottomRef.current = false;
          }}
          onScrollToIndexFailed={() => scrollToBottom(false)}
          ListEmptyComponent={
            isAuthenticated ? (
              <View style={{ padding: 24 }}>
                <Text style={{ color: colors.text, fontSize: 22, textAlign: 'center' }}>
                  {tr('chatEmptyTitle')}
                </Text>
                <Text style={{ color: colors.textMuted, textAlign: 'center', marginTop: 8 }}>
                  {tr('chatEmptyBody')}
                </Text>
              </View>
            ) : (
              <GuestEmptyState
                onPick={(prompt) => {
                  if (guest.gated) {
                    openAuthPreservingDraft(true);
                    return;
                  }
                  scrollToBottom();
                  void guest.send(prompt);
                }}
              />
            )
          }
        renderItem={({ item }) => {
          const rematched =
            item.role === 'user' && !item.local_image_uris?.length
              ? imagePreviewByContent.current[item.content]
              : undefined;
          return (
            <ChatBubble
              message={item}
              imageUris={rematched}
              onRetry={
                item.role === 'assistant'
                  ? () => {
                      const lastUser = [...messages].reverse().find((m) => m.role === 'user');
                      if (lastUser && isAuthenticated) void turn.send(lastUser.content);
                    }
                  : undefined
              }
            />
          );
        }}
          ListFooterComponent={
            <View>
              {turn.statusRows.map((s) => (
                <Text key={s.id} style={styles.gate} accessibilityLiveRegion="polite">
                  {s.text}
                </Text>
              ))}
              {turn.liveText ? (
                <ChatBubble
                  message={{
                    id: 'live-stream',
                    role: 'assistant',
                    content: turn.liveText,
                    created_at: Date.now() / 1000,
                  }}
                  showActions={false}
                />
              ) : null}
              {turn.cards.map((c) => (
                <ActivityCard
                  key={c.id}
                  card={c}
                  onApproveDraft={(token) => void turn.send('', { confirm_tool: token })}
                  onDiscard={() => owner.setProposedPatch(null)}
                  onOpenCm={() => onOpenArea('cm')}
                  onRetry={() => {
                    const lastUser = [...messages].reverse().find((m) => m.role === 'user');
                    if (lastUser) void turn.send(lastUser.content);
                  }}
                />
              ))}
              {isAuthenticated &&
              owner.proposedPatch?.confirmation_token &&
              !turn.cards.some((c) => c.kind === 'proposal') ? (
                <ActivityCard
                  card={{
                    id: 'legacy-proposal',
                    kind: 'proposal',
                    title: tr('proposedCmPatch'),
                    body: '',
                    status: 'pending_approval',
                    data: owner.proposedPatch as unknown as Record<string, unknown>,
                  }}
                  onApproveDraft={(token) => void turn.send('', { confirm_tool: token })}
                  onDiscard={() => {
                    owner.setProposedPatch(null);
                    owner.setPendingConfirm(null);
                  }}
                  onOpenCm={() => onOpenArea('cm')}
                />
              ) : null}
            </View>
          }
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
          onSend={() => void handleSend()}
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
        onOpenChat={(id) => void owner.openConversation(id)}
        onTogglePin={(id) => void togglePin(id)}
        onArchive={(id) => void owner.setArchived(id, true)}
        onUnarchive={(id) => void owner.setArchived(id, false)}
        onRename={(id, title) => void owner.renameConversation(id, title)}
        onDelete={(id) => void owner.deleteConversation(id)}
        onLogout={onLogout}
        onLogin={() => openAuthPreservingDraft(false)}
        onRegister={onRequestRegister}
        onOpenNotifications={isAuthenticated ? () => onOpenArea('notifications') : undefined}
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
