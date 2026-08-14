import { useCallback, useEffect, useRef } from 'react';
import { FlatList, Keyboard, Platform } from 'react-native';

/**
 * Stick-to-latest helpers for the non-inverted chat FlatList.
 * Re-scrolls on keyboard show so KAV height shrink does not cover the last message.
 *
 * Intentional jump (send / FAB) → scrollToBottom (arms stick).
 * Stream / layout growth → followBottomIfStuck (never re-arms; re-checks after rAF
 * so a user drag away from bottom is not yanked by a pending delta).
 * ChatMessageList must not re-arm stick from onScroll while the finger/momentum
 * gesture is active — otherwise near-bottom samples during the first pixels of
 * an upward drag re-enable follow and yank back to the live stream.
 */
export function useChatListScroll() {
  const listRef = useRef<FlatList>(null);
  const stickToBottomRef = useRef(false);

  /** Pin to latest and scroll — send, FAB, open chat, etc. */
  const scrollToBottom = useCallback((animated = true) => {
    stickToBottomRef.current = true;
    requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated }));
  }, []);

  /**
   * Follow the growing stream only while still stuck to bottom.
   * Must not re-arm stick — that would defeat onScrollBeginDrag during liveText.
   */
  const followBottomIfStuck = useCallback((animated = false) => {
    requestAnimationFrame(() => {
      if (!stickToBottomRef.current) return;
      listRef.current?.scrollToEnd({ animated });
    });
  }, []);

  const armOpenAtLatest = useCallback((opts?: { pinToLatest?: boolean }) => {
    if (opts?.pinToLatest === false) {
      stickToBottomRef.current = false;
      const run = () => listRef.current?.scrollToOffset({ offset: 0, animated: false });
      requestAnimationFrame(run);
      setTimeout(run, 50);
      setTimeout(run, 180);
      return;
    }
    stickToBottomRef.current = true;
    const run = (animated: boolean) => listRef.current?.scrollToEnd({ animated });
    requestAnimationFrame(() => run(false));
    setTimeout(() => run(false), 50);
    setTimeout(() => run(false), 180);
  }, []);

  useEffect(() => {
    const event = Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow';
    const sub = Keyboard.addListener(event, () => {
      // Re-check stick on every retry — user may scroll away while KAV settles.
      const run = (animated: boolean) => {
        if (!stickToBottomRef.current) return;
        listRef.current?.scrollToEnd({ animated });
      };
      requestAnimationFrame(() => run(false));
      setTimeout(() => run(false), 50);
      setTimeout(() => run(false), 120);
      setTimeout(() => run(true), 220);
    });
    return () => sub.remove();
  }, []);

  return { listRef, stickToBottomRef, scrollToBottom, followBottomIfStuck, armOpenAtLatest };
}
