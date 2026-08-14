/** Opening splash — full-screen #083A37 + centered sparkle (screenshot match). */

export const bootSplashTokens = {
  background: '#083A37',
  /** Matches expo-splash-screen `imageWidth` so JS and native paint the same mark. */
  markSize: 220,
  minDisplayMs: 900,
  minDisplayReducedMs: 320,
  exitFadeMs: 220,
} as const;
