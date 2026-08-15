/** Opening splash — full-screen #083A37 + centered sparkle (screenshot match). */

export const bootSplashTokens = {
  background: '#083A37',
  /** Matches expo-splash-screen `imageWidth` so JS and native paint the same mark. */
  markSize: 220,
  minDisplayMs: 900,
  minDisplayReducedMs: 320,
  exitFadeMs: 220,
  /**
   * Hard cap: leave splash even if auth/SecureStore never settles.
   * Chat may still be hydrating; do not block the first screen on API.
   */
  maxHoldMs: 2500,
} as const;

/** Delay until the branded splash may unmount. Never exceeds maxHoldMs. */
export function splashExitDelayMs(
  appReady: boolean,
  elapsedMs: number,
  minDisplayMs: number,
  maxHoldMs: number,
): number {
  const minWait = Math.max(0, minDisplayMs - elapsedMs);
  const maxWait = Math.max(0, maxHoldMs - elapsedMs);
  return appReady ? minWait : maxWait;
}
