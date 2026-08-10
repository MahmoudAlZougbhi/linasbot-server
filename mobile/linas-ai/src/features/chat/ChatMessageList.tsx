import { useCallback, useRef, useState, type RefObject } from 'react';
import {
  ActivityIndicator,
  FlatList,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Text,
  View,
} from 'react-native';

import type { ChatMessage } from '../../api/types';
import { useI18n } from '../../i18n/LanguageContext';
import { useTheme } from '../../theme';
import { ChatBubble } from './ChatBubble';
import { chatScreenStyles as styles } from './chatScreenStyles';
import { ChatStreamFooter } from './ChatStreamFooter';
import { GuestEmptyState } from './GuestEmptyState';
import { OwnerEmptyState } from './OwnerEmptyState';
import { ScrollToLatestFab } from './ScrollToLatestFab';
import type { ProposedPatch } from './useChatSession';
import type { StreamCard } from './v2/useOwnerStream';

const NEAR_BOTTOM_PX = 96;
const NEAR_TOP_PX = 72;

type Props = {
  listRef: RefObject<FlatList | null>;
  listKey: string;
  messages: ChatMessage[];
  isAuthenticated: boolean;
  stickToBottomRef: { current: boolean };
  scrollToBottom: (animated?: boolean) => void;
  imagePreviewByContent: { current: Record<string, string[]> };
  thinking: boolean;
  statusRows: { id: string; text: string }[];
  liveText: string;
  cards: StreamCard[];
  proposedPatch: ProposedPatch | null;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadOlder: () => void;
  onRetryAssistant: (content: string) => void;
  onApproveDraft: (token: string) => void;
  onDiscardProposal: () => void;
  onOpenCm: () => void;
  onGuestPrompt: (prompt: string) => void;
};

export function ChatMessageList({
  listRef,
  listKey,
  messages,
  isAuthenticated,
  stickToBottomRef,
  scrollToBottom,
  imagePreviewByContent,
  thinking,
  statusRows,
  liveText,
  cards,
  proposedPatch,
  hasMore,
  loadingMore,
  onLoadOlder,
  onRetryAssistant,
  onApproveDraft,
  onDiscardProposal,
  onOpenCm,
  onGuestPrompt,
}: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();
  const [showJump, setShowJump] = useState(false);
  const loadGateRef = useRef(false);

  // Allow another older-page fetch only after the previous one finishes.
  if (!loadingMore) loadGateRef.current = false;

  const onScroll = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      const { contentOffset, contentSize, layoutMeasurement } = e.nativeEvent;
      const distanceFromBottom =
        contentSize.height - layoutMeasurement.height - contentOffset.y;
      const nearBottom = distanceFromBottom <= NEAR_BOTTOM_PX;
      stickToBottomRef.current = nearBottom;
      setShowJump(!nearBottom && contentSize.height > layoutMeasurement.height + 8);

      if (contentOffset.y <= NEAR_TOP_PX && hasMore && !loadingMore && !loadGateRef.current) {
        loadGateRef.current = true;
        onLoadOlder();
      }
    },
    [hasMore, loadingMore, onLoadOlder, stickToBottomRef],
  );

  return (
    <View style={styles.flex}>
      <FlatList
        key={listKey}
        ref={listRef}
        style={styles.flex}
        data={messages}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="interactive"
        scrollEventThrottle={16}
        onScroll={onScroll}
        maintainVisibleContentPosition={{ minIndexForVisible: 0 }}
        onContentSizeChange={() => {
          if (stickToBottomRef.current) scrollToBottom(false);
        }}
        onLayout={() => {
          if (stickToBottomRef.current) scrollToBottom(false);
        }}
        onScrollBeginDrag={() => {
          stickToBottomRef.current = false;
        }}
        onScrollToIndexFailed={() => scrollToBottom(false)}
        ListHeaderComponent={
          loadingMore ? (
            <ActivityIndicator color={colors.accent} style={{ marginVertical: 12 }} />
          ) : hasMore ? (
            <Text style={{ color: colors.textMuted, textAlign: 'center', marginBottom: 8, fontSize: 12 }}>
              Scroll up for older messages
            </Text>
          ) : null
        }
        ListEmptyComponent={
          isAuthenticated ? (
            <OwnerEmptyState />
          ) : (
            <GuestEmptyState onPick={onGuestPrompt} />
          )
        }
        renderItem={({ item, index }) => {
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
                      const prevUser = [...messages.slice(0, index)]
                        .reverse()
                        .find((m) => m.role === 'user');
                      if (prevUser) onRetryAssistant(prevUser.content);
                    }
                  : undefined
              }
            />
          );
        }}
        ListFooterComponent={
          <ChatStreamFooter
            thinking={thinking}
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
      <ScrollToLatestFab
        visible={showJump}
        onPress={() => {
          setShowJump(false);
          scrollToBottom(true);
        }}
      />
    </View>
  );
}
