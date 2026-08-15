import { useCallback, useRef, useState, type RefObject } from 'react';
import {
  ActivityIndicator,
  FlatList,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Text,
  View,
} from 'react-native';

import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ChatMessage } from '../../api/types';
import { useI18n } from '../../i18n/LanguageContext';
import { useTheme } from '../../theme';
import type { CmProposalReview } from '../cm/cmProposalReview';
import { ChatBubble } from './ChatBubble';
import { CHAT_LIST_TOP_CLEARANCE } from './ChatHeader';
import { chatScreenStyles as styles } from './chatScreenStyles';
import { ChatStreamFooter } from './ChatStreamFooter';
import { GuestEmptyState } from './GuestEmptyState';
import { OwnerEmptyState } from './OwnerEmptyState';
import { OwnerWelcomeChips, type OwnerWelcomeChip } from './OwnerWelcomeChips';
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
  /** Stream/layout growth only — must not re-arm stick after user scrolls away. */
  followBottomIfStuck: (animated?: boolean) => void;
  imagePreviewByContent: { current: Record<string, string[]> };
  thinking: boolean;
  thinkingLabel: string;
  statusRows: { id: string; text: string }[];
  liveText: string;
  cards: StreamCard[];
  proposedPatch: ProposedPatch | null;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadOlder: () => void;
  onRetryAssistant: (content: string) => void;
  onApproveDraft: (token: string, opts?: { delete_ids?: string[] }) => void;
  onDiscardProposal: (token?: string) => void;
  onEditProposal?: (proposalId: string) => void;
  onOpenCm: (review?: CmProposalReview) => void;
  onGuestPrompt: (prompt: string) => void;
  showOwnerWelcomeChips?: boolean;
  onOwnerWelcomeChip?: (chip: OwnerWelcomeChip) => void;
  seedTypewriterMessageId?: string | null;
  onSeedTypewriterDone?: () => void;
};

export function ChatMessageList({
  listRef,
  listKey,
  messages,
  isAuthenticated,
  stickToBottomRef,
  scrollToBottom,
  followBottomIfStuck,
  imagePreviewByContent,
  thinking,
  thinkingLabel,
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
  onEditProposal,
  onOpenCm,
  onGuestPrompt,
  showOwnerWelcomeChips = false,
  onOwnerWelcomeChip,
  seedTypewriterMessageId = null,
  onSeedTypewriterDone,
}: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [showJump, setShowJump] = useState(false);
  const loadGateRef = useRef(false);
  /** True from finger-down through momentum end — blocks onScroll from re-arming stick. */
  const userInteractingRef = useRef(false);
  const interactFallbackRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Allow another older-page fetch only after the previous one finishes.
  if (!loadingMore) loadGateRef.current = false;

  const clearInteractFallback = useCallback(() => {
    if (interactFallbackRef.current) {
      clearTimeout(interactFallbackRef.current);
      interactFallbackRef.current = null;
    }
  }, []);

  const distanceFromBottom = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const { contentOffset, contentSize, layoutMeasurement } = e.nativeEvent;
    return contentSize.height - layoutMeasurement.height - contentOffset.y;
  };

  const latchStickIfNearBottom = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      if (distanceFromBottom(e) <= NEAR_BOTTOM_PX) stickToBottomRef.current = true;
    },
    [stickToBottomRef],
  );

  const endUserInteraction = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      clearInteractFallback();
      userInteractingRef.current = false;
      latchStickIfNearBottom(e);
    },
    [clearInteractFallback, latchStickIfNearBottom],
  );

  const onScroll = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      const { contentOffset, contentSize, layoutMeasurement } = e.nativeEvent;
      const nearBottom = distanceFromBottom(e) <= NEAR_BOTTOM_PX;
      // Re-arm only when the user is not mid-gesture. During drag/momentum, beginDrag
      // cleared stick — onScroll must not flip it back while still within NEAR_BOTTOM_PX
      // (that race re-enabled followBottomIfStuck and yanked the list to the live stream).
      // Clearing on distance alone is still wrong: keyboard dismiss grows the viewport
      // and distanceFromBottom jumps without a user drag (#144).
      if (nearBottom && !userInteractingRef.current) stickToBottomRef.current = true;
      setShowJump(!nearBottom && contentSize.height > layoutMeasurement.height + 8);

      if (contentOffset.y <= NEAR_TOP_PX && hasMore && !loadingMore && !loadGateRef.current) {
        loadGateRef.current = true;
        onLoadOlder();
      }
    },
    [hasMore, loadingMore, onLoadOlder, stickToBottomRef],
  );

  const onScrollBeginDrag = useCallback(() => {
    clearInteractFallback();
    userInteractingRef.current = true;
    stickToBottomRef.current = false;
  }, [clearInteractFallback, stickToBottomRef]);

  const onScrollEndDrag = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      // If fling continues, wait for onMomentumScrollEnd before re-arming.
      const vy = e.nativeEvent.velocity?.y ?? 0;
      if (Math.abs(vy) < 0.05) {
        endUserInteraction(e);
        return;
      }
      // Some Android paths skip momentum end — don't leave interacting latched forever.
      clearInteractFallback();
      interactFallbackRef.current = setTimeout(() => {
        userInteractingRef.current = false;
        interactFallbackRef.current = null;
      }, 400);
    },
    [clearInteractFallback, endUserInteraction],
  );

  const onMomentumScrollEnd = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      endUserInteraction(e);
    },
    [endUserInteraction],
  );

  return (
    <View style={[styles.flex, styles.ltr]}>
      <FlatList
        key={listKey}
        ref={listRef}
        style={styles.flex}
        data={messages}
        keyExtractor={(item) => item.id}
        contentContainerStyle={[
          styles.list,
          { paddingTop: insets.top + CHAT_LIST_TOP_CLEARANCE },
        ]}
        contentInsetAdjustmentBehavior="never"
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="interactive"
        scrollEventThrottle={16}
        onScroll={onScroll}
        maintainVisibleContentPosition={{ minIndexForVisible: 0 }}
        onContentSizeChange={() => {
          followBottomIfStuck(false);
        }}
        onLayout={() => {
          followBottomIfStuck(false);
        }}
        onScrollBeginDrag={onScrollBeginDrag}
        onScrollEndDrag={onScrollEndDrag}
        onMomentumScrollEnd={onMomentumScrollEnd}
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
              userLabel={tr('chatYouLabel')}
              linasLabel={tr('chatLinasLabel')}
              imageUris={rematched}
              typewriter={item.id === seedTypewriterMessageId}
              onTypewriterDone={
                item.id === seedTypewriterMessageId ? onSeedTypewriterDone : undefined
              }
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
          <>
            <ChatStreamFooter
              thinking={thinking}
              thinkingLabel={thinkingLabel}
              statusRows={statusRows}
              liveText={liveText}
              cards={cards}
              proposedPatch={proposedPatch}
              proposedCmPatchLabel={tr('proposedCmPatch')}
              onApproveDraft={onApproveDraft}
              onDiscardProposal={onDiscardProposal}
              onEditProposal={onEditProposal}
              onOpenCm={onOpenCm}
              onRetryLast={() => {
                const lastUser = [...messages].reverse().find((m) => m.role === 'user');
                if (lastUser) onRetryAssistant(lastUser.content);
              }}
            />
            {showOwnerWelcomeChips && onOwnerWelcomeChip ? (
              <OwnerWelcomeChips onPick={onOwnerWelcomeChip} />
            ) : null}
          </>
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
