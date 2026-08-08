import { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { usePublicLandingLocale } from '../../contexts/PublicLandingLocaleContext';

/** @typedef {'idle' | 'walking' | 'greeting' | 'laughing' | 'helping' | 'annoyed' | 'bored'} MascotMood */

const LONG_PRESS_MS = 550;
const PROXIMITY_PX = 110;
const FLOOR_BOTTOM = 'max(0.75rem, env(safe-area-inset-bottom, 0.75rem))';

/**
 * @param {number} min
 * @param {number} max
 */
function randomBetween(min, max) {
  return min + Math.random() * (max - min);
}

/**
 * @param {number} fromX
 * @param {number} toX
 */
function walkDurationSec(fromX, toX) {
  return Math.min(6, Math.max(2.2, Math.abs(toX - fromX) * 0.11));
}

/**
 * Futuristic walking Linas mascot for the public landing page.
 * @returns {import('react').JSX.Element}
 */
const LinasBotMascot = () => {
  const { locale, mascotSpeech } = usePublicLandingLocale();
  const rootRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const longPressTimerRef = useRef(/** @type {number | null} */ (null));
  const lastTapRef = useRef(0);
  const moodLockUntilRef = useRef(0);
  const moodRef = useRef(/** @type {MascotMood} */ ('greeting'));
  const positionRef = useRef(18);

  const [reduceMotion, setReduceMotion] = useState(false);
  const [mood, setMood] = useState(/** @type {MascotMood} */ ('greeting'));
  const [speech, setSpeech] = useState(mascotSpeech.greeting);
  const [facingLeft, setFacingLeft] = useState(false);
  const [positionX, setPositionX] = useState(18);
  const [walkDuration, setWalkDuration] = useState(2.4);

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

  const pickWalkTarget = useCallback(() => randomBetween(10, 88), []);

  const walkTo = useCallback((/** @type {number} */ targetX) => {
    const fromX = positionRef.current;
    setFacingLeft(targetX < fromX);
    setWalkDuration(walkDurationSec(fromX, targetX));
    positionRef.current = targetX;
    setPositionX(targetX);
    updateMood('walking');
  }, [updateMood]);

  useEffect(() => {
    if (['laughing', 'helping', 'annoyed', 'walking', 'bored'].includes(moodRef.current)) return;
    setSpeech(mascotSpeech.greeting);
    if (moodRef.current === 'idle' || moodRef.current === 'greeting') {
      lockMood('greeting', mascotSpeech.greeting, 2200);
    }
  }, [locale, mascotSpeech, lockMood]);

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
      lockMood('greeting', mascotSpeech.greeting, 3200);
    }, 500);
    return () => window.clearTimeout(intro);
  }, [lockMood, mascotSpeech.greeting, reduceMotion]);

  useEffect(() => {
    if (reduceMotion) return undefined;

    const wanderTimer = window.setInterval(() => {
      if (Date.now() < moodLockUntilRef.current) return;
      if (moodRef.current === 'laughing') return;
      walkTo(pickWalkTarget());
    }, 12000);

    return () => window.clearInterval(wanderTimer);
  }, [pickWalkTarget, reduceMotion, walkTo]);

  useEffect(() => {
    if (reduceMotion || mood !== 'walking') return undefined;
    const done = window.setTimeout(() => {
      if (Date.now() < moodLockUntilRef.current) return;
      updateMood('greeting');
      setSpeech(mascotSpeech.greeting);
      window.setTimeout(() => {
        if (Date.now() < moodLockUntilRef.current) return;
        updateMood('idle');
        setSpeech('');
      }, 1800);
    }, walkDuration * 1000);
    return () => window.clearTimeout(done);
  }, [mascotSpeech.greeting, mood, reduceMotion, updateMood, walkDuration]);

  useEffect(() => {
    if (reduceMotion) return undefined;

    const boredTimer = window.setInterval(() => {
      if (Date.now() < moodLockUntilRef.current) return;
      if (moodRef.current !== 'idle') return;
      updateMood('bored');
      setSpeech(mascotSpeech.bored);
      window.setTimeout(() => {
        if (Date.now() < moodLockUntilRef.current) return;
        updateMood('idle');
        setSpeech('');
      }, 2600);
    }, 14000);

    return () => window.clearInterval(boredTimer);
  }, [mascotSpeech.bored, reduceMotion, updateMood]);

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
        setSpeech(mascotSpeech.laughing);
      } else if (moodRef.current === 'laughing') {
        updateMood('idle');
        setSpeech('');
      }
    };

    window.addEventListener('pointermove', onPointerMove, { passive: true });
    return () => window.removeEventListener('pointermove', onPointerMove);
  }, [mascotSpeech.laughing, reduceMotion, updateMood]);

  const clearLongPress = useCallback(() => {
    if (longPressTimerRef.current) {
      window.clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  }, []);

  const onHelping = useCallback(() => {
    clearLongPress();
    walkTo(randomBetween(42, 58));
    lockMood('helping', mascotSpeech.helping, 3600);
    window.setTimeout(() => {
      if (Date.now() < moodLockUntilRef.current) return;
      updateMood('idle');
      setSpeech('');
    }, 3600);
  }, [clearLongPress, lockMood, mascotSpeech.helping, updateMood, walkTo]);

  const onAnnoyed = useCallback(() => {
    clearLongPress();
    lockMood('annoyed', mascotSpeech.annoyed, 3200);
    window.setTimeout(() => {
      if (Date.now() < moodLockUntilRef.current) return;
      updateMood('idle');
      setSpeech('');
    }, 3200);
  }, [clearLongPress, lockMood, mascotSpeech.annoyed, updateMood]);

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

  const walking = mood === 'walking';
  const waving = mood === 'greeting' || mood === 'helping';
  const laughing = mood === 'laughing';
  const annoyed = mood === 'annoyed';
  const bored = mood === 'bored';

  return (
    <motion.div
      ref={rootRef}
      className="pointer-events-none fixed z-30 select-none"
      style={{ bottom: FLOOR_BOTTOM, left: `${positionX}%` }}
      animate={{ left: `${positionX}%` }}
      transition={
        reduceMotion
          ? { duration: 0 }
          : { duration: walkDuration, ease: 'linear' }
      }
    >
      <motion.div
        className="pointer-events-auto relative flex -translate-x-1/2 flex-col items-center touch-manipulation"
        animate={
          reduceMotion
            ? {}
            : {
                rotate: annoyed ? [0, -3, 3, -2, 2, 0] : laughing ? [0, -1.5, 1.5, 0] : 0,
              }
        }
        transition={{
          duration: annoyed ? 0.45 : 0.35,
          repeat: annoyed || laughing ? Number.POSITIVE_INFINITY : 0,
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
        aria-label={mascotSpeech.ariaLabel}
        title={mascotSpeech.hint}
      >
        <AnimatePresence>
          {speech ? (
            <motion.div
              key={`${locale}-${speech}`}
              initial={{ opacity: 0, y: 6, scale: 0.94 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 4, scale: 0.96 }}
              dir={locale === 'ar' ? 'rtl' : 'ltr'}
              className="absolute bottom-[calc(100%+0.4rem)] left-1/2 z-10 w-max max-w-[min(17rem,calc(100vw-2rem))] -translate-x-1/2 rounded-2xl border border-cyan-200/80 bg-slate-950/90 px-3 py-2 text-center text-xs font-semibold leading-snug text-cyan-50 shadow-[0_0_24px_rgba(34,211,238,0.25)] backdrop-blur-md"
              aria-live="polite"
            >
              {speech}
              <span
                className="absolute left-1/2 top-full h-2 w-2 -translate-x-1/2 -translate-y-1 rotate-45 border-b border-r border-cyan-200/80 bg-slate-950/90"
                aria-hidden="true"
              />
            </motion.div>
          ) : null}
        </AnimatePresence>

        <div
          className={`relative transition-transform duration-300 ${walking ? 'linas-bot-walk-bob' : ''}`}
          style={{ transform: facingLeft ? 'scaleX(-1)' : 'scaleX(1)' }}
        >
          <svg
            width="86"
            height="108"
            viewBox="0 0 86 108"
            className="drop-shadow-[0_12px_28px_rgba(14,165,233,0.28)]"
            aria-hidden="true"
          >
            <defs>
              <linearGradient id="linas-future-body" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#0ea5e9" />
                <stop offset="55%" stopColor="#6366f1" />
                <stop offset="100%" stopColor="#d946ef" />
              </linearGradient>
              <linearGradient id="linas-future-visor" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#22d3ee" />
                <stop offset="100%" stopColor="#a78bfa" />
              </linearGradient>
              <filter id="linas-glow" x="-40%" y="-40%" width="180%" height="180%">
                <feGaussianBlur stdDeviation="2.2" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            <ellipse cx="43" cy="104" rx="22" ry="3.5" fill="rgba(15,23,42,0.18)" />

            <g className={walking ? 'linas-leg-right' : ''}>
              <rect x="47" y="78" width="7" height="18" rx="3.5" fill="#1e293b" stroke="#38bdf8" strokeWidth="1" />
              <rect x="45" y="93" width="11" height="6" rx="3" fill="#0f172a" stroke="#22d3ee" strokeWidth="1" />
            </g>
            <g className={walking ? 'linas-leg-left' : ''}>
              <rect x="32" y="78" width="7" height="18" rx="3.5" fill="#1e293b" stroke="#38bdf8" strokeWidth="1" />
              <rect x="30" y="93" width="11" height="6" rx="3" fill="#0f172a" stroke="#22d3ee" strokeWidth="1" />
            </g>

            <rect x="27" y="52" width="32" height="28" rx="11" fill="url(#linas-future-body)" stroke="#67e8f9" strokeWidth="1.2" />
            <rect x="31" y="58" width="24" height="3" rx="1.5" fill="rgba(255,255,255,0.35)" />
            <circle cx="37" cy="68" r="2" fill="#22d3ee" filter="url(#linas-glow)" />
            <circle cx="43" cy="70" r="2" fill="#c084fc" filter="url(#linas-glow)" />
            <circle cx="49" cy="68" r="2" fill="#22d3ee" filter="url(#linas-glow)" />

            <rect x="22" y="58" width="14" height="6" rx="3" fill="#1e293b" stroke="#94a3b8" strokeWidth="1" />
            <g className={waving ? 'linas-arm-wave-future' : ''}>
              <rect x="50" y="56" width="14" height="6" rx="3" fill="#1e293b" stroke="#94a3b8" strokeWidth="1" />
            </g>

            <rect x="30" y="24" width="26" height="30" rx="12" fill="#0f172a" stroke="#38bdf8" strokeWidth="1.5" />
            <rect x="33" y="30" width="20" height="12" rx="6" fill="url(#linas-future-visor)" opacity="0.95" />
            <line x1="43" y1="8" x2="43" y2="2" stroke="#67e8f9" strokeWidth="2" strokeLinecap="round" />
            <circle cx="43" cy="2" r="2.5" fill={waving ? '#fbbf24' : '#22d3ee'} filter="url(#linas-glow)" />

            {laughing ? (
              <>
                <path d="M35 28 Q38 25 41 28" stroke="#ecfeff" strokeWidth="1.8" fill="none" strokeLinecap="round" />
                <path d="M45 28 Q48 25 51 28" stroke="#ecfeff" strokeWidth="1.8" fill="none" strokeLinecap="round" />
                <path d="M36 38 Q43 44 50 38" stroke="#ecfeff" strokeWidth="2.2" fill="none" strokeLinecap="round" />
              </>
            ) : annoyed ? (
              <>
                <path d="M35 29 L40 33" stroke="#ecfeff" strokeWidth="1.8" strokeLinecap="round" />
                <path d="M40 29 L35 33" stroke="#ecfeff" strokeWidth="1.8" strokeLinecap="round" />
                <path d="M46 29 L51 33" stroke="#ecfeff" strokeWidth="1.8" strokeLinecap="round" />
                <path d="M51 29 L46 33" stroke="#ecfeff" strokeWidth="1.8" strokeLinecap="round" />
                <path d="M37 40 Q43 36 49 40" stroke="#ecfeff" strokeWidth="2" fill="none" strokeLinecap="round" />
              </>
            ) : bored ? (
              <>
                <ellipse cx="38" cy="30" rx="3" ry="1" fill="#ecfeff" />
                <ellipse cx="48" cy="30" rx="3" ry="1" fill="#ecfeff" />
                <ellipse cx="43" cy="40" rx="4.5" ry="2.5" fill="#ecfeff" />
              </>
            ) : (
              <>
                <circle cx="38" cy="29" r="1.2" fill="#fff" />
                <circle cx="48" cy="29" r="1.2" fill="#fff" />
                <path d="M37 38 Q43 41 49 38" stroke="#ecfeff" strokeWidth="1.8" fill="none" strokeLinecap="round" />
              </>
            )}

            <text x="43" y="76" textAnchor="middle" fontSize="6.5" fontWeight="700" fill="#e0f2fe" letterSpacing="0.08em">
              LINAS
            </text>
          </svg>
        </div>
      </motion.div>
    </motion.div>
  );
};

export default LinasBotMascot;
