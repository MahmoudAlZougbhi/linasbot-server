/**
 * Soft light Linas palette — calm premium AI (ChatGPT/Claude-inspired surfaces).
 * Refined blue accent, no black heaviness, no neon.
 */
export const colors = {
  bg: '#F7F8FA',
  bgElevated: '#FFFFFF',
  surface: '#FFFFFF',
  surfaceAlt: '#EEF2F7',
  surfaceGlass: 'rgba(255, 255, 255, 0.92)',
  text: '#0F172A',
  textMuted: '#64748B',
  textDim: '#94A3B8',
  accent: '#2563EB',
  accentSoft: '#DBEAFE',
  accentGlow: 'rgba(37, 99, 235, 0.10)',
  onAccent: '#FFFFFF',
  mint: '#0D9488',
  mintSoft: '#CCFBF1',
  danger: '#DC2626',
  warning: '#D97706',
  border: '#E2E8F0',
  borderSoft: '#EEF2F7',
  input: '#F1F5F9',
  bubbleUser: '#2563EB',
  bubbleUserText: '#FFFFFF',
  bubbleAi: '#FFFFFF',
  overlay: 'rgba(15, 23, 42, 0.40)',
  success: '#0D9488',
  banner: '#EFF6FF',
  bannerBorder: '#BFDBFE',
} as const;

export type ColorName = keyof typeof colors;
