import { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';

/** @typedef {'idle' | 'wandering' | 'greeting' | 'laughing' | 'helping' | 'annoyed' | 'bored'} MascotMood */

const LONG_PRESS_MS = 550;
const PROXIMITY_PX = 110;
const SPEECH = {
  greeting: "Hi! I'm Linas — your reply buddy 👋",
  helping: 'Ok dear — حاه ظبطلك!',
  annoyed: 'Shou hal long press?! 😤',
  bored: '*yawn*… waiting for customers…',
};

/**
 * @param {number} min
 * @param {number} max
 */
function randomBetween(min, max) {
  return min + Math.random() * (max - min);
}

/**
 * Small autonomous Linas robot mascot for the public landing page.
 * @returns {import('react').JSX.Element}
 */
const LinasBotMascot = () => {
  const rootRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const longPressTimerRef = useRef(/** @type {number | null} */ (null));
  const lastTapRef = useRef(0);
  const moodLockUntilRef = useRef(0);
  const moodRef = useRef(/** @type {MascotMood} */ ('greeting'));
  const positionRef = useRef({ x: 72, y: 78 });

  const [reduceMotion, setReduceMotion] = useState(false);
  const [mood, setMood] = useState(/** @type {MascotMood} */ ('greeting'));
  const [speech, setSpeech] = useState(SPEECH.greeting);
  const [facingLeft, setFacingLeft] = useState(false);
  const [position, setPosition] = useState({ x: 72, y: 78 });

  const updateMood = useCallback(/** @param {MascotMood} nextMood */ (nextMood) => {
    moodRef.current = nextMood;
    setMood(nextMood);
  }, []);

  const lockMood = useCallback(/**
   * @param {MascotMood} nextMood
   * @param {string} message
   * @param {number} [lockMs]
   */ (nextMood, message, lockMs = 2800) => {
    moodLockUntilRef.current = Date.now() + lockMs;
    updateMood(nextMood);
    if (message) setSpeech(message);
  }, [updateMood]);

  const pickWanderSpot = useCallback(() => {
    const marginX = 12;
    const marginY = 14;
    const maxX = Math.max(marginX + 4, 88 - marginX);
    const maxY = Math.max(marginY + 4, 86 - marginY);
    return {
      x: randomBetween(marginX, maxX),
      y: randomBetween(marginY, maxY),
    };
  }, []);

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined;
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduceMotion(media.matches);
    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    if (reduceMotion) return undefined;
    const intro = window.setTimeout(() => {
      lockMood('greeting', SPEECH.greeting, 3200);
    }, 400);
    return () => window.clearTimeout(intro);
  }, [lockMood, reduceMotion]);

  useEffect(() => {
    if (reduceMotion) return undefined;

    const wanderTimer = window.setInterval(() => {
      if (Date.now() < moodLockUntilRef.current) return;
      if (moodRef.current === 'laughing') return;
      const next = pickWanderSpot();
      setFacingLeft(next.x < positionRef.current.x);
      positionRef.current = next;
      setPosition(next);
      updateMood('wandering');
      window.setTimeout(() => {
        if (Date.now() < moodLockUntilRef.current) return;
        updateMood('greeting');
        setSpeech(SPEECH.greeting);
        window.setTimeout(() => {
          if (Date.now() < moodLockUntilRef.current) return;
          updateMood('idle');
          setSpeech('');
        }, 1800);
      }, 2200);
    }, 11000);

    return () => window.clearInterval(wanderTimer);
  }, [pickWanderSpot, reduceMotion, updateMood]);

  useEffect(() => {
    if (reduceMotion) return undefined;

    const boredTimer = window.setInterval(() => {
      if (Date.now() < moodLockUntilRef.current) return;
      if (moodRef.current !== 'idle') return;
      updateMood('bored');
      setSpeech(SPEECH.bored);
      window.setTimeout(() => {
        if (Date.now() < moodLockUntilRef.current) return;
        updateMood('idle');
        setSpeech('');
      }, 2600);
    }, 12000);

    return () => window.clearInterval(boredTimer);
  }, [reduceMotion, updateMood]);

  useEffect(() => {
    if (reduceMotion) return undefined;

    const onPointerMove = (/** @type {PointerEvent} */ event) => {
      if (Date.now() < moodLockUntilRef.current) return;
      const node = rootRef.current;
      if (!node) return;
      const rect = node.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      const distance = Math.hypot(event.clientX - centerX, event.clientY - centerY);
      if (distance < PROXIMITY_PX) {
        updateMood('laughing');
        setSpeech('Hehehe! 😄');
      } else if (moodRef.current === 'laughing') {
        updateMood('idle');
        setSpeech('');
      }
    };

    window.addEventListener('pointermove', onPointerMove, { passive: true });
    return () => window.removeEventListener('pointermove', onPointerMove);
  }, [reduceMotion, updateMood]);

  const clearLongPress = useCallback(() => {
    if (longPressTimerRef.current) {
      window.clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  }, []);

  const onHelping = useCallback(() => {
    clearLongPress();
    const target = { x: randomBetween(58, 72), y: randomBetween(62, 74) };
    setFacingLeft(target.x < positionRef.current.x);
    positionRef.current = target;
    setPosition(target);
    lockMood('helping', SPEECH.helping, 3600);
    window.setTimeout(() => {
      if (Date.now() < moodLockUntilRef.current) return;
      updateMood('idle');
      setSpeech('');
    }, 3600);
  }, [clearLongPress, lockMood, updateMood]);

  const onAnnoyed = useCallback(() => {
    clearLongPress();
    lockMood('annoyed', SPEECH.annoyed, 3200);
    window.setTimeout(() => {
      if (Date.now() < moodLockUntilRef.current) return;
      updateMood('idle');
      setSpeech('');
    }, 3200);
  }, [clearLongPress, lockMood, updateMood]);

  const onPointerDown = useCallback(() => {
    clearLongPress();
    longPressTimerRef.current = window.setTimeout(onAnnoyed, LONG_PRESS_MS);
  }, [clearLongPress, onAnnoyed]);

  const onPointerUp = useCallback(() => {
    clearLongPress();
  }, [clearLongPress]);

  const onTap = useCallback(() => {
    const now = Date.now();
    if (now - lastTapRef.current < 320) {
      lastTapRef.current = 0;
      onHelping();
      return;
    }
    lastTapRef.current = now;
  }, [onHelping]);

  const waving = mood === 'greeting' || mood === 'helping';
  const laughing = mood === 'laughing';
  const annoyed = mood === 'annoyed';
  const bored = mood === 'bored';

  return (
    <div
      ref={rootRef}
      className="pointer-events-none fixed z-30 select-none"
      style={{
        left: `${position.x}%`,
        top: `${position.y}%`,
        transform: 'translate(-50%, -50%)',
      }}
    >
      <motion.div
        className="pointer-events-auto relative flex flex-col items-center touch-manipulation"
        animate={
          reduceMotion
            ? {}
            : {
                y: laughing ? [0, -5, 0, -4, 0] : bored ? [0, 2, 0] : mood === 'wandering' ? [0, -2, 0] : 0,
                rotate: annoyed ? [0, -4, 4, -3, 3, 0] : laughing ? [0, -2, 2, 0] : 0,
              }
        }
        transition={{
          duration: laughing ? 0.45 : annoyed ? 0.5 : 1.6,
          repeat: laughing || annoyed ? Number.POSITIVE_INFINITY : 0,
          ease: 'easeInOut',
        }}
        onPointerDown={onPointerDown}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
        onPointerCancel={onPointerUp}
        onClick={onTap}
        onDoubleClick={(event) => {
          event.preventDefault();
          onHelping();
        }}
        role="img"
        aria-label="Linas, the friendly AI assistant character"
        title="Linas — double-tap: حاه ظبطلك · long-press: he gets annoyed"
      >
        <AnimatePresence>
          {speech ? (
            <motion.div
              key={speech}
              initial={{ opacity: 0, y: 8, scale: 0.92 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 6, scale: 0.95 }}
              className="absolute bottom-[calc(100%+0.35rem)] left-1/2 z-10 w-max max-w-[min(16rem,calc(100vw-2rem))] -translate-x-1/2 rounded-2xl border border-white/70 bg-white/95 px-3 py-2 text-center text-xs font-semibold leading-snug text-slate-800 shadow-lg backdrop-blur-sm"
              aria-live="polite"
            >
              {speech}
              <span
                className="absolute left-1/2 top-full h-2 w-2 -translate-x-1/2 -translate-y-1 rotate-45 border-b border-r border-white/70 bg-white/95"
                aria-hidden="true"
              />
            </motion.div>
          ) : null}
        </AnimatePresence>

        <div
          className="relative transition-transform duration-300"
          style={{ transform: facingLeft ? 'scaleX(-1)' : 'scaleX(1)' }}
        >
          <svg
            width="78"
            height="88"
            viewBox="0 0 78 88"
            className="drop-shadow-[0_10px_22px_rgba(15,23,42,0.22)]"
            aria-hidden="true"
          >
            <defs>
              <linearGradient id="linas-body" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#38bdf8" />
                <stop offset="100%" stopColor="#c084fc" />
              </linearGradient>
            </defs>
            <ellipse cx="39" cy="82" rx="20" ry="4" fill="rgba(15,23,42,0.12)" />
            <rect x="24" y="48" width="30" height="24" rx="10" fill="url(#linas-body)" />
            <circle cx="39" cy="30" r="20" fill="#f8fafc" stroke="#cbd5e1" strokeWidth="2" />
            <line x1="39" y1="10" x2="39" y2="3" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" />
            <circle cx="39" cy="3" r="3" fill={waving ? '#fbbf24' : '#38bdf8'} />
            <circle cx="31" cy="28" r="4.5" fill="#0f172a" />
            <circle cx="47" cy="28" r="4.5" fill="#0f172a" />
            {laughing ? (
              <>
                <path d="M27 24 Q31 20 35 24" stroke="#0f172a" strokeWidth="2" fill="none" strokeLinecap="round" />
                <path d="M43 24 Q47 20 51 24" stroke="#0f172a" strokeWidth="2" fill="none" strokeLinecap="round" />
                <path d="M30 36 Q39 44 48 36" stroke="#0f172a" strokeWidth="2.5" fill="none" strokeLinecap="round" />
              </>
            ) : annoyed ? (
              <>
                <path d="M28 26 L34 30" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" />
                <path d="M34 26 L28 30" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" />
                <path d="M44 26 L50 30" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" />
                <path d="M50 26 L44 30" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" />
                <path d="M32 38 Q39 34 46 38" stroke="#0f172a" strokeWidth="2.5" fill="none" strokeLinecap="round" />
              </>
            ) : bored ? (
              <>
                <ellipse cx="31" cy="28" rx="3.5" ry="1.2" fill="#0f172a" />
                <ellipse cx="47" cy="28" rx="3.5" ry="1.2" fill="#0f172a" />
                <ellipse cx="39" cy="38" rx="5" ry="3" fill="#0f172a" />
              </>
            ) : (
              <>
                <circle cx="32" cy="27" r="1.2" fill="#fff" />
                <circle cx="48" cy="27" r="1.2" fill="#fff" />
                <path d="M32 37 Q39 41 46 37" stroke="#0f172a" strokeWidth="2" fill="none" strokeLinecap="round" />
              </>
            )}
            <g className={waving ? 'linas-arm-wave' : ''}>
              <rect x="10" y="52" width="16" height="7" rx="3.5" fill="#e2e8f0" stroke="#94a3b8" />
            </g>
            <rect x="52" y="52" width="16" height="7" rx="3.5" fill="#e2e8f0" stroke="#94a3b8" />
            <circle cx="30" cy="58" r="2" fill="#38bdf8" />
            <circle cx="39" cy="60" r="2" fill="#c084fc" />
            <circle cx="48" cy="58" r="2" fill="#38bdf8" />
            <text x="39" y="66" textAnchor="middle" fontSize="7" fontWeight="700" fill="#0f172a">
              LINAS
            </text>
          </svg>
        </div>
      </motion.div>
    </div>
  );
};

export default LinasBotMascot;
