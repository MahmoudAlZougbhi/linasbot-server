import type { RefObject } from 'react';
import { FlatList, Text, View } from 'react-native';

import type { ChatMessage } from '../../api/types';
import { useI18n } from '../../i18n/LanguageContext';
import { useTheme } from '../../theme';
import { ChatBubble } from './ChatBubble';
import { chatScreenStyles as styles } from './chatScreenStyles';
import { ChatStreamFooter } from './ChatStreamFooter';
import { GuestEmptyState } from './GuestEmptyState';
import type { ProposedPatch } from './useChatSession';
import type { StreamCard } from './v2/useOwnerStream';

type Props = {
  listRef: RefObject<FlatList | null>;
  messages: ChatMessage[];
  isAuthenticated: boolean;
  stickToBottomRef: { current: boolean };
  scrollToBottom: (animated?: boolean) => void;
  imagePreviewByContent: { current: Record<string, string[]> };
  statusRows: { id: string; text: string }[];
  liveText: string;
  cards: StreamCard[];
  proposedPatch: ProposedPatch | null;
  onRetryAssistant: (content: string) => void;
  onApproveDraft: (token: string) => void;
  onDiscardProposal: () => void;
  onOpenCm: () => void;
  onGuestPrompt: (prompt: string) => void;
};

export function ChatMessageList({
  listRef,
  messages,
  isAuthenticated,
  stickToBottomRef,
  scrollToBottom,
  imagePreviewByContent,
  statusRows,
  liveText,
  cards,
  proposedPatch,
  onRetryAssistant,
  onApproveDraft,
  onDiscardProposal,
  onOpenCm,
  onGuestPrompt,
}: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();

  return (
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
          <GuestEmptyState onPick={onGuestPrompt} />
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
                    if (lastUser && isAuthenticated) onRetryAssistant(lastUser.content);
                  }
                : undefined
            }
          />
        );
      }}
      ListFooterComponent={
        <ChatStreamFooter
          statusRows={statusRows}
          liveText={liveText}
          cards={cards}
          proposedPatch={proposedPatch}
          proposedCmPatchLabel={tr('proposedCmPatch')}
          onApproveDraft={onApproveDraft}
          onDiscardProposal={onDiscardProposal}
          onOpenCm={onOpenCm}
          onRetryLast={() => {
            const lastUser = [...messages].reverse().find((m) => m.role === 'user');
            if (lastUser) onRetryAssistant(lastUser.content);
          }}
        />
      }
    />
  );
}
