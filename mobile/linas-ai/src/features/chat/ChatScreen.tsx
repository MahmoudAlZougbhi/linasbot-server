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
import { colors, fonts } from '../../theme';
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
    if (action === 'add_cm') {
      onOpenArea('cm');
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

  return (
    <GradientBackground>
      <ChatHeader
        title={session.title}
        onOpenHistory={() => setHistoryOpen(true)}
        onOpenControl={() => setControlOpen(true)}
      />

      {session.error ? (
        <Pressable onPress={() => void session.bootstrap()}>
          <Text style={styles.error}>{session.error}</Text>
        </Pressable>
      ) : null}
      {voiceError ? <Text style={styles.error}>{voiceError}</Text> : null}

      <FlatList
        data={session.messages}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <EmptyState
            title="Start with Linas AI"
            body="Ask to configure Content Management, check usage, or draft a post."
          />
        }
        renderItem={({ item }) => <ChatBubble message={item} />}
      />

      {session.pendingConfirm ? (
        <Pressable
          style={styles.confirm}
          onPress={() => void session.send('', session.pendingConfirm ?? undefined)}
        >
          <Text style={styles.confirmText}>Confirm {session.pendingConfirm}</Text>
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
  confirm: {
    marginHorizontal: 16,
    marginBottom: 8,
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
});
