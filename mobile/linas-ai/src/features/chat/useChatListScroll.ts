import { useCallback, useEffect, useRef } from 'react';
import { FlatList, Keyboard, Platform } from 'react-native';

/**
 * Stick-to-latest helpers for the non-inverted chat FlatList.
 * Re-scrolls on keyboard show so KAV height shrink does not cover the last message.
 */
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

  useEffect(() => {
    const event = Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow';
    const sub = Keyboard.addListener(event, () => {
      if (!stickToBottomRef.current) return;
      // KeyboardAvoidingView padding settles across the animation — retry like open-at-latest.
      const run = () => listRef.current?.scrollToEnd({ animated: false });
      requestAnimationFrame(run);
      setTimeout(run, 50);
      setTimeout(run, 120);
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 220);
    });
    return () => sub.remove();
  }, []);

  return { listRef, stickToBottomRef, scrollToBottom, armOpenAtLatest };
}
