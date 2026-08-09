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
import { ControlCenterDrawer } from '../control/ControlCenterDrawer';
import type { ControlArea } from '../control/controlAreas';
import { ChatBubble } from './ChatBubble';
import { ChatComposer } from './ChatComposer';
import { ChatHeader } from './ChatHeader';
import { ComposerPlusSheet, type PlusAction } from './ComposerPlusSheet';
import { HistoryDrawer } from './HistoryDrawer';
import { useChatSession } from './useChatSession';
import { usePinnedChats } from './usePinnedChats';
import { useVoiceDraft } from './useVoiceDraft';

type Props = {
  isPlatformOwner: boolean;
  onOpenArea: (area: ControlArea) => void;
  onLogout: () => void;
};

export function ChatScreen({ isPlatformOwner, onOpenArea, onLogout }: Props) {
  const { tr } = useI18n();
  const session = useChatSession();
  const [userId, setUserId] = useState<string | null>(null);
  const { pinnedIds, togglePin } = usePinnedChats(userId);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [controlOpen, setControlOpen] = useState(false);
  const [plusOpen, setPlusOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const { voiceState, voiceError, toggleVoice } = useVoiceDraft((text) => {
    setDraft((prev) => (prev ? `${prev} ${text}` : text));
  });

  useEffect(() => {
    void tokenStore.getUser().then((u) => setUserId(u?.id ?? null));
  }, []);

  function handlePlus(action: PlusAction) {
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

  if (session.loading) {
    return (
      <GradientBackground>
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent} />
        </View>
      </GradientBackground>
    );
  }

  const preview = session.proposedPatch?.preview;
  const changedKeys = Array.isArray(preview?.changed_keys)
    ? (preview?.changed_keys as string[]).join(', ')
    : '';

  return (
    <GradientBackground>
      <ChatHeader
        title={session.title}
        onOpenHistory={() => setHistoryOpen(true)}
        onOpenControl={() => setControlOpen(true)}
      />

      {session.error ? (
        <Pressable onPress={() => void session.bootstrap()}>
          <Text style={styles.error}>{tr(session.error === 'retry' ? 'retry' : 'messageFailed')}</Text>
        </Pressable>
      ) : null}
      {voiceError ? <Text style={styles.error}>{voiceError}</Text> : null}

      <FlatList
        data={session.messages}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <EmptyState title={tr('chatEmptyTitle')} body={tr('chatEmptyBody')} />
        }
        renderItem={({ item }) => <ChatBubble message={item} />}
      />

      {session.quickActions.length ? (
        <View style={styles.chips}>
          {session.quickActions.slice(0, 4).map((a) => (
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

      {session.proposedPatch?.confirmation_token ? (
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

      {session.pendingConfirm && !session.proposedPatch ? (
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
        sending={session.sending}
        voiceState={voiceState}
        onPlus={() => setPlusOpen(true)}
        onToggleVoice={() => void toggleVoice()}
        onSend={() => {
          const text = draft;
          setDraft('');
          void session.send(text);
        }}
      />

      <HistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        history={session.history}
        pinnedIds={pinnedIds}
        activeId={session.conversationId}
        onNewChat={() => {
          void session.newChat().then(() => setHistoryOpen(false));
        }}
        onOpen={(id) => {
          void session.openConversation(id).then(() => setHistoryOpen(false));
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
    backgroundColor: colors.surfaceAlt,
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
