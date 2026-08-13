/**
 * PDF handoff visual tokens — teal/mint accent, clean white/dark parity.
 * Sample business names from the PDF are never stored here.
 */
export type ThemeColors = {
  bg: string;
  bgElevated: string;
  surface: string;
  surfaceAlt: string;
  surfaceGlass: string;
  text: string;
  textMuted: string;
  textDim: string;
  accent: string;
  accentSoft: string;
  accentGlow: string;
  accentDeep: string;
  onAccent: string;
  mint: string;
  mintSoft: string;
  danger: string;
  warning: string;
  border: string;
  borderSoft: string;
  input: string;
  bubbleUser: string;
  bubbleUserText: string;
  bubbleAi: string;
  bubbleAiText: string;
  overlay: string;
  success: string;
  banner: string;
  bannerBorder: string;
  progressTrack: string;
  progressFill: string;
  activeRow: string;
  activeIndicator: string;
  /** Side drawer panel background. */
  drawerSurface: string;
  /** Legacy alias used by a few forms — maps to accentSoft. */
  lavender: string;
};

export const lightColors: ThemeColors = {
  bg: '#F7FBFB',
  bgElevated: '#FFFFFF',
  surface: '#FFFFFF',
  surfaceAlt: '#EEF6F5',
  surfaceGlass: 'rgba(255, 255, 255, 0.96)',
  text: '#10221A',
  textMuted: '#5B6B6A',
  textDim: '#8A9A98',
  accent: '#0D9488',
  accentSoft: '#CCFBF1',
  accentGlow: 'rgba(13, 148, 136, 0.14)',
  accentDeep: '#0F766E',
  onAccent: '#FFFFFF',
  mint: '#0D9488',
  mintSoft: '#CCFBF1',
  danger: '#DC2626',
  warning: '#D97706',
  border: '#D7E5E3',
  borderSoft: '#E8F1F0',
  input: '#F3F8F7',
  bubbleUser: '#E6F7F4',
  bubbleUserText: '#10221A',
  bubbleAi: '#FFFFFF',
  bubbleAiText: '#10221A',
  overlay: 'rgba(16, 34, 26, 0.42)',
  success: '#0D9488',
  banner: '#F3F8F7',
  bannerBorder: '#D7E5E3',
  progressTrack: '#D7E5E3',
  progressFill: '#0D9488',
  activeRow: '#ECEEEE',
  activeIndicator: '#0D9488',
  drawerSurface: '#F2F4F4',
  lavender: '#CCFBF1',
};

export const darkColors: ThemeColors = {
  bg: '#0B1413',
  bgElevated: '#121C1B',
  surface: '#162220',
  surfaceAlt: '#1C2B29',
  surfaceGlass: 'rgba(18, 28, 27, 0.96)',
  text: '#F2FAF8',
  textMuted: '#A7B8B5',
  textDim: '#7A8E8B',
  accent: '#2DD4BF',
  accentSoft: '#134E4A',
  accentGlow: 'rgba(45, 212, 191, 0.18)',
  accentDeep: '#5EEAD4',
  onAccent: '#042F2E',
  mint: '#2DD4BF',
  mintSoft: '#134E4A',
  danger: '#F87171',
  warning: '#FBBF24',
  border: '#2A3B39',
  borderSoft: '#1E2C2A',
  input: '#1A2624',
  bubbleUser: '#134E4A',
  bubbleUserText: '#F2FAF8',
  bubbleAi: '#162220',
  bubbleAiText: '#F2FAF8',
  overlay: 'rgba(0, 0, 0, 0.55)',
  success: '#2DD4BF',
  banner: '#1A2624',
  bannerBorder: '#2A3B39',
  progressTrack: '#2A3B39',
  progressFill: '#2DD4BF',
  activeRow: '#1E2C2A',
  activeIndicator: '#2DD4BF',
  drawerSurface: '#121C1B',
  lavender: '#134E4A',
};

export type ThemeMode = 'light' | 'dark' | 'system';
