import { useEffect, useState } from 'react';
import { HERO_CHAT_LINES } from './heroChatLines';

const TYPING_MS = 1300;
const HOLD_MS = 2000;
const LOOP_PAUSE_MS = 4500;

function isJsdom() {
  return typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent);
}

/**
 * Plays the owner-teaching thread one turn at a time (knowledge, product, appointment).
 * Tests run in jsdom and get the full thread immediately.
 */
export default function useHeroChatPlayback() {
  const skipPlay = isJsdom();
  const [visible, setVisible] = useState(skipPlay ? HERO_CHAT_LINES.length : 0);
  const [typing, setTyping] = useState(false);

  useEffect(() => {
    if (skipPlay) return undefined;
    const ctrl = { cancelled: false, timer: 0 };

    /** @param {number} ms */
    const wait = (ms) =>
      new Promise((resolve) => {
        ctrl.timer = window.setTimeout(resolve, ms);
      });

    const run = async () => {
      while (!ctrl.cancelled) {
        for (let index = 0; index < HERO_CHAT_LINES.length; index += 1) {
          if (ctrl.cancelled) return;
          const line = HERO_CHAT_LINES[index];
          if (!line) return;
          if (line.role === 'linas') {
            setTyping(true);
            await wait(TYPING_MS);
            if (ctrl.cancelled) return;
            setTyping(false);
          }
          setVisible(index + 1);
          await wait(HOLD_MS);
        }
        await wait(LOOP_PAUSE_MS);
        if (ctrl.cancelled) return;
        setVisible(0);
        setTyping(false);
      }
    };

    run();
    return () => {
      ctrl.cancelled = true;
      window.clearTimeout(ctrl.timer);
    };
  }, [skipPlay]);

  return {
    typing,
    lines: HERO_CHAT_LINES.slice(0, visible),
  };
}
