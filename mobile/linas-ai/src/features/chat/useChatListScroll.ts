import { useCallback, useRef } from 'react';
import type { FlatList } from 'react-native';

/** Stick-to-bottom helpers for owner/guest chat lists. */
export function useChatListScroll() {
  const listRef = useRef<FlatList>(null);
  const stickToBottomRef = useRef(true);

  const scrollToBottom = useCallback((animated = true) => {
    stickToBottomRef.current = true;
    requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated }));
  }, []);

  const armOpenAtLatest = useCallback(() => {
    stickToBottomRef.current = true;
    const run = (animated: boolean) => listRef.current?.scrollToEnd({ animated });
    requestAnimationFrame(() => run(false));
    setTimeout(() => run(false), 50);
    setTimeout(() => run(false), 180);
  }, []);

  return { listRef, stickToBottomRef, scrollToBottom, armOpenAtLatest };
}
