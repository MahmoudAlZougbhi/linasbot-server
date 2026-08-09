import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, Text, TextInput, View } from 'react-native';

import { EmptyState } from '../../components/EmptyState';
import { GradientBackground } from '../../components/GradientBackground';
import { tokenStore } from '../../auth/tokenStore';
import { useI18n } from '../../i18n/LanguageContext';
import { colors } from '../../theme';
import { AuthGateModal } from '../auth/AuthGateModal';
import { ControlCenterDrawer } from '../control/ControlCenterDrawer';
import type { ControlArea } from '../control/controlAreas';
import { ChatBubble } from './ChatBubble';
import { ChatComposer } from './ChatComposer';
import { ChatHeader } from './ChatHeader';
import { chatScreenStyles as styles } from './chatScreenStyles';
import { ComposerPlusSheet, type PlusAction } from './ComposerPlusSheet';
import { GuestBanner } from './GuestBanner';
import { HistoryDrawer } from './HistoryDrawer';
import { useChatSession } from './useChatSession';
import { useGuestChatSession } from './useGuestChatSession';
import { usePinnedChats } from './usePinnedChats';
import { useVoiceDraft } from './useVoiceDraft';
import { ActivityCard } from './v2/ActivityCard';
import { ChoiceChips } from './v2/ChoiceChips';
import { pickDocumentAttachment, pickImageAttachment, type PendingFile } from './v2/pickAttachment';
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
  isPlatformOwner,
  onOpenArea,
  onLogout,
  onRequestLogin,
  onRequestRegister,
}: Props) {
  const { tr } = useI18n();
  const owner = useChatSession(isAuthenticated);
  const guest = useGuestChatSession(!isAuthenticated);
  const session = isAuthenticated ? owner : null;
  const turn = useStreamingTurn(owner.conversationId, owner.bootstrap);
  const [userId, setUserId] = useState<string | null>(null);
  const { pinnedIds, togglePin } = usePinnedChats(userId);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [controlOpen, setControlOpen] = useState(false);
  const [plusOpen, setPlusOpen] = useState(false);
  const [authGate, setAuthGate] = useState(false);
  const [authGateReason, setAuthGateReason] = useState<string | undefined>();
  const [draft, setDraft] = useState('');
  const [pendingFile, setPendingFile] = useState<PendingFile | null>(null);
  const [choiceBusy, setChoiceBusy] = useState(false);
  const composerInputRef = useRef<TextInput>(null);
  const { voiceState, voiceError, toggleVoice, metering } = useVoiceDraft((text) => {
    setDraft((prev) => (prev ? `${prev} ${text}` : text));
    requestAnimationFrame(() => composerInputRef.current?.focus());
  });

  useEffect(() => {
    if (!isAuthenticated) {
      setUserId(null);
      return;
    }
    void tokenStore.getUser().then((u) => setUserId(u?.id ?? null));
  }, [isAuthenticated]);

  async function handlePlus(action: PlusAction) {
    if (!isAuthenticated) {
      setAuthGate(true);
      return;
    }
    if (action === 'add_cm' || action === 'review_setup') {
      onOpenArea('cm');
      return;
    }
    if (action === 'check_usage') {
      onOpenArea('usage');
      return;
    }
    if (action === 'attach_image') {
      setPendingFile(await pickImageAttachment());
      return;
    }
    if (action === 'attach_document') {
      setPendingFile(await pickDocumentAttachment());
    }
  }

  const loading = isAuthenticated ? owner.loading : guest.loading;
  const messages = isAuthenticated ? owner.messages : guest.messages;
  const sending = isAuthenticated ? owner.sending || turn.streaming : guest.sending;
  const error = isAuthenticated ? owner.error : guest.error;
  const title = isAuthenticated ? owner.title : guest.title;
  const preview = session?.proposedPatch?.preview;
  const changedKeys = Array.isArray(preview?.changed_keys)
    ? (preview?.changed_keys as string[]).join(', ')
    : '';

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
      <ChatHeader
        title={title}
        online
        avatarState={
          voiceState === 'recording'
            ? 'listening'
            : turn.thinking || turn.streaming
              ? 'thinking'
              : voiceState === 'transcribing'
                ? 'thinking'
                : 'idle'
        }
        onOpenHistory={() => (isAuthenticated ? setHistoryOpen(true) : setAuthGate(true))}
        onOpenControl={() => (isAuthenticated ? setControlOpen(true) : setAuthGate(true))}
      />

      {!isAuthenticated ? (
        <GuestBanner
          remaining={guest.questionsRemaining}
          max={guest.maxQuestions}
          gated={guest.gated}
          onLogin={onRequestLogin}
        />
      ) : null}

      {error ? (
        <Pressable onPress={() => void (isAuthenticated ? owner.bootstrap() : guest.bootstrap())}>
          <Text style={styles.error}>
            {tr(
              error === 'retry' || error === 'guestWordLimit' || error === 'guestModelUnavailable'
                ? error
                : 'messageFailed',
            )}
          </Text>
        </Pressable>
      ) : null}
      {voiceError ? <Text style={styles.error}>{voiceError}</Text> : null}

      <FlatList
        data={messages}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <EmptyState
            showMascot={false}
            title={tr(isAuthenticated ? 'chatEmptyTitle' : 'guestChatEmptyTitle')}
            body={tr(isAuthenticated ? 'chatEmptyBody' : 'guestChatEmptyBody')}
          />
        }
        renderItem={({ item }) => <ChatBubble message={item} />}
        ListFooterComponent={
          <View>
            {turn.thinking ? <Text style={styles.gate}>Thinking…</Text> : null}
            {turn.statusRows.map((s) => (
              <Text key={s.id} style={styles.gate}>
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
              />
            ) : null}
            {turn.cards.map((c) => (
              <ActivityCard key={c.id} card={c} />
            ))}
          </View>
        }
      />

      {isAuthenticated && session?.quickActions.length ? (
        <View style={styles.chips}>
          {session.quickActions
            .filter((a) => a.id !== 'create' && a.id !== 'comments')
            .slice(0, 4)
            .map((a) => (
              <Pressable key={a.id} style={styles.chip} onPress={() => onOpenArea(a.id as ControlArea)}>
                <Text style={styles.chipText}>{a.label}</Text>
              </Pressable>
            ))}
        </View>
      ) : null}

      {isAuthenticated ? (
        <ChoiceChips
          choices={turn.choices}
          disabled={choiceBusy || turn.streaming}
          onSelect={(c) => {
            if (!turn.choiceSetId || choiceBusy) return;
            setChoiceBusy(true);
            void turn
              .send(c.label, { choice_id: c.id, choice_set_id: turn.choiceSetId })
              .finally(() => setChoiceBusy(false));
          }}
        />
      ) : null}

      {pendingFile ? (
        <View style={styles.patchCard}>
          <Text style={styles.patchTitle}>{pendingFile.name}</Text>
          <Pressable style={styles.reject} onPress={() => setPendingFile(null)}>
            <Text style={styles.rejectText}>{tr('rejectAction')}</Text>
          </Pressable>
        </View>
      ) : null}

      {isAuthenticated && session?.proposedPatch?.confirmation_token ? (
        <View style={styles.patchCard}>
          <Text style={styles.patchTitle}>{tr('proposedCmPatch')}</Text>
          {changedKeys ? <Text style={styles.patchBody}>Keys: {changedKeys}</Text> : null}
          <View style={styles.patchActions}>
            <Pressable
              style={styles.confirm}
              onPress={() => void turn.send('', { confirm_tool: session.proposedPatch?.confirmation_token })}
            >
              <Text style={styles.confirmText}>{tr('confirmAction')}</Text>
            </Pressable>
            <Pressable
              style={styles.reject}
              onPress={() => {
                session.setProposedPatch(null);
                session.setPendingConfirm(null);
              }}
            >
              <Text style={styles.rejectText}>{tr('rejectAction')}</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      <ChatComposer
        draft={draft}
        onChangeDraft={setDraft}
        sending={sending || (!isAuthenticated && guest.gated)}
        canSendWithAttachment={Boolean(pendingFile)}
        voiceState={isAuthenticated ? voiceState : 'idle'}
        metering={isAuthenticated ? metering : null}
        inputRef={composerInputRef}
        onPlus={() => (isAuthenticated ? setPlusOpen(true) : setAuthGate(true))}
        onToggleVoice={() => {
          if (!isAuthenticated) {
            setAuthGate(true);
            return;
          }
          void toggleVoice();
        }}
        onStop={turn.streaming ? () => turn.stop() : undefined}
        onSend={() => {
          if (!isAuthenticated && guest.gated) {
            onRequestLogin();
            return;
          }
          if (voiceState === 'recording' || voiceState === 'transcribing') return;
          const text = draft;
          setDraft('');
          if (!isAuthenticated) {
            void guest.send(text);
            return;
          }
          void (async () => {
            let attachmentIds: string[] | undefined;
            if (pendingFile) {
              try {
                const up = await uploadOwnerAttachment(pendingFile);
                attachmentIds = [up.attachment_id];
              } catch {
                /* upload error surfaced on next turn */
              }
              setPendingFile(null);
            }
            await turn.send(text || (attachmentIds ? 'Please analyze this attachment.' : ''), {
              attachment_ids: attachmentIds,
            });
          })();
        }}
      />

      {isAuthenticated ? (
        <>
          <HistoryDrawer
            open={historyOpen}
            onClose={() => setHistoryOpen(false)}
            history={owner.history}
            pinnedIds={pinnedIds}
            activeId={owner.conversationId}
            onNewChat={() => void owner.newChat().then(() => setHistoryOpen(false))}
            onOpen={(id) => void owner.openConversation(id).then(() => setHistoryOpen(false))}
            onTogglePin={(id) => void togglePin(id)}
          />
          <ControlCenterDrawer
            open={controlOpen}
            onClose={() => setControlOpen(false)}
            isPlatformOwner={isPlatformOwner}
            onOpen={(area) => {
              setControlOpen(false);
              onOpenArea(area);
            }}
            onLogout={onLogout}
          />
          <ComposerPlusSheet open={plusOpen} onClose={() => setPlusOpen(false)} onAction={(a) => void handlePlus(a)} />
        </>
      ) : null}

      <AuthGateModal
        visible={authGate}
        reason={authGateReason}
        onClose={() => {
          setAuthGate(false);
          setAuthGateReason(undefined);
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
