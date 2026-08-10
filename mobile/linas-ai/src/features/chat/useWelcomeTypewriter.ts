import { useEffect, useState } from 'react';
import { AppState } from 'react-native';

const TYPE_MS = 18;
const CURSOR_MS = 520;

/**
 * One-shot typewriter for the seeded New Chat greeting bubble.
 * Owner chats always seed a greeting on create, so an empty-state typewriter
 * loop would type then vanish when the seed arrives — this types the greeting
 * itself instead. Pauses while backgrounded; cleans up on unmount / disable.
 */
export function useOnceTypewriter(text: string, enabled: boolean) {
  const [shown, setShown] = useState(enabled ? '' : text);
  const [done, setDone] = useState(!enabled);
  const [cursorOn, setCursorOn] = useState(enabled);

  useEffect(() => {
    if (!enabled) {
      setShown(text);
      setDone(true);
      setCursorOn(false);
      return;
    }

    let cancelled = false;
    let finished = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let appActive = AppState.currentState === 'active';
    let i = 0;

    const clearTimer = () => {
      if (timer !== undefined) clearTimeout(timer);
      timer = undefined;
    };

    const wait = (ms: number, next: () => void) => {
      clearTimer();
      timer = setTimeout(() => {
        if (!cancelled && appActive) next();
      }, ms);
    };

    const step = () => {
      if (cancelled || !appActive || finished) return;
      if (i < text.length) {
        i += 1;
        setShown(text.slice(0, i));
        wait(TYPE_MS, step);
        return;
      }
      finished = true;
      setDone(true);
      setCursorOn(false);
    };

    setShown('');
    setDone(false);
    setCursorOn(true);
    step();

    const appSub = AppState.addEventListener('change', (next) => {
      const wasActive = appActive;
      appActive = next === 'active';
      if (!appActive) {
        clearTimer();
        return;
      }
      if (!wasActive && !cancelled && !finished) step();
    });

    const cursorTimer = setInterval(() => {
      if (!cancelled && !finished) setCursorOn((v) => !v);
    }, CURSOR_MS);

    return () => {
      cancelled = true;
      clearTimer();
      clearInterval(cursorTimer);
      appSub.remove();
    };
  }, [enabled, text]);

  return { shown, done, cursorOn };
}
