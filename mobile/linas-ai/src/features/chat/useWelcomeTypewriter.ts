import { useEffect, useState } from 'react';
import { AppState } from 'react-native';

const TYPE_MS = 34;
const DELETE_MS = 22;
const HOLD_FULL_MS = 1900;
const HOLD_PARTIAL_MS = 420;
const CURSOR_MS = 520;

type CursorLine = 'title' | 'body' | 'none';

type Phase =
  | 'typeTitle'
  | 'typeBody'
  | 'holdFull'
  | 'deleteBody'
  | 'deleteTitle'
  | 'holdPartial';

/**
 * ChatGPT-like type → hold → partial delete → retype loop for New Chat welcome copy.
 * Pauses while the app is backgrounded; cleans up timers on unmount / disable.
 */
export function useWelcomeTypewriter(title: string, body: string, enabled: boolean) {
  const [titleShown, setTitleShown] = useState(enabled ? '' : title);
  const [bodyShown, setBodyShown] = useState(enabled ? '' : body);
  const [cursorLine, setCursorLine] = useState<CursorLine>(enabled ? 'title' : 'none');
  const [cursorOn, setCursorOn] = useState(enabled);

  useEffect(() => {
    if (!enabled) {
      setTitleShown(title);
      setBodyShown(body);
      setCursorLine('none');
      setCursorOn(false);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let appActive = AppState.currentState === 'active';
    let titleI = 0;
    let bodyI = 0;
    let phase: Phase = 'typeTitle';
    const keep = Math.max(6, Math.floor(title.length * 0.42));

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
      if (cancelled || !appActive) return;

      switch (phase) {
        case 'typeTitle': {
          setCursorLine('title');
          if (titleI < title.length) {
            titleI += 1;
            setTitleShown(title.slice(0, titleI));
            wait(TYPE_MS, step);
            return;
          }
          phase = 'typeBody';
          wait(140, step);
          return;
        }
        case 'typeBody': {
          setCursorLine('body');
          if (bodyI < body.length) {
            bodyI += 1;
            setBodyShown(body.slice(0, bodyI));
            wait(TYPE_MS, step);
            return;
          }
          phase = 'holdFull';
          wait(HOLD_FULL_MS, step);
          return;
        }
        case 'holdFull':
          phase = 'deleteBody';
          step();
          return;
        case 'deleteBody': {
          setCursorLine('body');
          if (bodyI > 0) {
            bodyI -= 1;
            setBodyShown(body.slice(0, bodyI));
            wait(DELETE_MS, step);
            return;
          }
          phase = 'deleteTitle';
          wait(70, step);
          return;
        }
        case 'deleteTitle': {
          setCursorLine('title');
          if (titleI > keep) {
            titleI -= 1;
            setTitleShown(title.slice(0, titleI));
            wait(DELETE_MS, step);
            return;
          }
          phase = 'holdPartial';
          wait(HOLD_PARTIAL_MS, step);
          return;
        }
        case 'holdPartial':
          phase = 'typeTitle';
          wait(60, step);
          return;
      }
    };

    setTitleShown('');
    setBodyShown('');
    setCursorLine('title');
    setCursorOn(true);
    step();

    const appSub = AppState.addEventListener('change', (next) => {
      const wasActive = appActive;
      appActive = next === 'active';
      if (!appActive) {
        clearTimer();
        return;
      }
      if (!wasActive && !cancelled) step();
    });

    const cursorTimer = setInterval(() => {
      if (!cancelled) setCursorOn((v) => !v);
    }, CURSOR_MS);

    return () => {
      cancelled = true;
      clearTimer();
      clearInterval(cursorTimer);
      appSub.remove();
    };
  }, [body, enabled, title]);

  return { titleShown, bodyShown, cursorLine, cursorOn };
}
