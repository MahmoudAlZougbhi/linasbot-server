import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { EmptyState } from '../../components/EmptyState';
import { GradientBackground } from '../../components/GradientBackground';
import { tokenStore } from '../../auth/tokenStore';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import { AuthGateModal } from '../auth/AuthGateModal';
import { ControlCenterDrawer } from '../control/ControlCenterDrawer';
import type { ControlArea } from '../control/controlAreas';
import { ChatBubble } from './ChatBubble';
import { ChatComposer } from './ChatComposer';
import { ChatHeader } from './ChatHeader';
import { ComposerPlusSheet, type PlusAction } from './ComposerPlusSheet';
import { GuestBanner } from './GuestBanner';
import { HistoryDrawer } from './HistoryDrawer';
import { useChatSession } from './useChatSession';
import { useGuestChatSession } from './useGuestChatSession';
import { usePinnedChats } from './usePinnedChats';
import { useVoiceDraft } from './useVoiceDraft';

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
  const [userId, setUserId] = useState<string | null>(null);
  const { pinnedIds, togglePin } = usePinnedChats(userId);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [controlOpen, setControlOpen] = useState(false);
  const [plusOpen, setPlusOpen] = useState(false);
  const [authGate, setAuthGate] = useState(false);
  const [draft, setDraft] = useState('');
  const { voiceState, voiceError, toggleVoice } = useVoiceDraft((text) => {
    setDraft((prev) => (prev ? `${prev} ${text}` : text));
  });

  useEffect(() => {
    if (!isAuthenticated) {
      setUserId(null);
      return;
    }
    void tokenStore.getUser().then((u) => setUserId(u?.id ?? null));
  }, [isAuthenticated]);

  function requireAuth() {
    setAuthGate(true);
  }

  function handlePlus(action: PlusAction) {
    if (!isAuthenticated) {
      requireAuth();
      return;
    }
    if (action === 'create_post') {
      onOpenArea('create');
      return;
    }
    if (action === 'add_cm' || action === 'review_setup') {
      onOpenArea('cm');
      return;
    }
    if (action === 'check_usage') {
      onOpenArea('usage');
    }
  }

  const loading = isAuthenticated ? owner.loading : guest.loading;
  const messages = isAuthenticated ? owner.messages : guest.messages;
  const sending = isAuthenticated ? owner.sending : guest.sending;
  const error = isAuthenticated ? owner.error : guest.error;
  const title = isAuthenticated ? owner.title : guest.title;

  if (loading) {
    return (
      <GradientBackground>
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent} />
        </View>
      </GradientBackground>
    );
  }

  const preview = session?.proposedPatch?.preview;
  const changedKeys = Array.isArray(preview?.changed_keys)
    ? (preview?.changed_keys as string[]).join(', ')
    : '';

  return (
    <GradientBackground>
      <ChatHeader
        title={title}
        onOpenHistory={() => {
          if (!isAuthenticated) {
            requireAuth();
            return;
          }
          setHistoryOpen(true);
        }}
        onOpenControl={() => {
          if (!isAuthenticated) {
            requireAuth();
            return;
          }
          setControlOpen(true);
        }}
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
        <Pressable
          onPress={() => void (isAuthenticated ? owner.bootstrap() : guest.bootstrap())}
        >
          <Text style={styles.error}>
            {tr(
              error === 'retry'
                ? 'retry'
                : error === 'guestWordLimit'
                  ? 'guestWordLimit'
                  : 'messageFailed',
            )}
          </Text>
        </Pressable>
      ) : null}
      {voiceError ? <Text style={styles.error}>{voiceError}</Text> : null}
      {!isAuthenticated && guest.gateText ? (
        <Text style={styles.gate}>{guest.gateText}</Text>
      ) : null}

      <FlatList
        data={messages}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <EmptyState
            title={tr(isAuthenticated ? 'chatEmptyTitle' : 'guestChatEmptyTitle')}
            body={tr(isAuthenticated ? 'chatEmptyBody' : 'guestChatEmptyBody')}
          />
        }
        renderItem={({ item }) => <ChatBubble message={item} />}
      />

      {isAuthenticated && session?.quickActions.length ? (
        <View style={styles.chips}>
          {session.quickActions
            .filter((a) => a.id !== 'comments')
            .slice(0, 4)
            .map((a) => (
              <Pressable
                key={a.id}
                style={styles.chip}
                onPress={() => onOpenArea(a.id as ControlArea)}
              >
                <Text style={styles.chipText}>{a.label}</Text>
              </Pressable>
            ))}
        </View>
      ) : null}

      {isAuthenticated && session?.proposedPatch?.confirmation_token ? (
        <View style={styles.patchCard}>
          <Text style={styles.patchTitle}>{tr('proposedCmPatch')}</Text>
          {changedKeys ? <Text style={styles.patchBody}>Keys: {changedKeys}</Text> : null}
          <View style={styles.patchActions}>
            <Pressable
              style={styles.confirm}
              onPress={() =>
                void session.send('', session.proposedPatch?.confirmation_token ?? undefined)
              }
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

      {isAuthenticated && session?.pendingConfirm && !session.proposedPatch ? (
        <Pressable
          style={styles.confirm}
          onPress={() => void session.send('', session.pendingConfirm ?? undefined)}
        >
          <Text style={styles.confirmText}>
            {tr('confirmAction')} {session.pendingConfirm}
          </Text>
        </Pressable>
      ) : null}

      <ChatComposer
        draft={draft}
        onChangeDraft={setDraft}
        sending={sending || (!isAuthenticated && guest.gated)}
        voiceState={isAuthenticated ? voiceState : 'idle'}
        onPlus={() => {
          if (!isAuthenticated) {
            requireAuth();
            return;
          }
          setPlusOpen(true);
        }}
        onToggleVoice={() => {
          if (!isAuthenticated) {
            requireAuth();
            return;
          }
          void toggleVoice();
        }}
        onSend={() => {
          if (!isAuthenticated && guest.gated) {
            onRequestLogin();
            return;
          }
          const text = draft;
          setDraft('');
          if (isAuthenticated) {
            void owner.send(text);
          } else {
            void guest.send(text);
          }
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
            onNewChat={() => {
              void owner.newChat().then(() => setHistoryOpen(false));
            }}
            onOpen={(id) => {
              void owner.openConversation(id).then(() => setHistoryOpen(false));
            }}
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
          <ComposerPlusSheet
            open={plusOpen}
            onClose={() => setPlusOpen(false)}
            onAction={handlePlus}
          />
        </>
      ) : null}

      <AuthGateModal
        visible={authGate}
        onClose={() => setAuthGate(false)}
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

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  list: { padding: 16, paddingBottom: 28, flexGrow: 1 },
  error: {
    color: colors.danger,
    fontFamily: fonts.body,
    paddingHorizontal: 16,
    paddingTop: 8,
  },
  gate: {
    color: colors.warning,
    fontFamily: fonts.body,
    paddingHorizontal: 16,
    paddingTop: 6,
    fontSize: 13,
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    paddingHorizontal: 14,
    marginBottom: 8,
  },
  chip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.bgElevated,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  chipText: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 12 },
  patchCard: {
    marginHorizontal: 16,
    marginBottom: 8,
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    padding: spacing.md,
    borderColor: colors.accent,
    borderWidth: 1,
    gap: 8,
  },
  patchTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 14 },
  patchBody: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12 },
  patchActions: { flexDirection: 'row', gap: 8 },
  confirm: {
    flex: 1,
    backgroundColor: colors.accentSoft,
    borderRadius: 14,
    padding: 12,
    borderColor: colors.accent,
    borderWidth: 1,
  },
  confirmText: {
    color: colors.accent,
    fontFamily: fonts.bodyMedium,
    fontWeight: '700',
    textAlign: 'center',
  },
  reject: {
    flex: 1,
    borderRadius: 14,
    padding: 12,
    borderColor: colors.border,
    borderWidth: 1,
  },
  rejectText: {
    color: colors.textMuted,
    fontFamily: fonts.bodyMedium,
    textAlign: 'center',
  },
});
