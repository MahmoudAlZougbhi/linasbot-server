/**
 * Soft futuristic Linas brand — lavender / violet / indigo / white + cyan accents.
 * Approved brand sheet is source of truth (overrides generic “avoid purple” defaults).
 */
export const colors = {
  bg: '#F7F4FC',
  bgElevated: '#FFFFFF',
  surface: '#FFFFFF',
  surfaceAlt: '#EFE8F8',
  surfaceGlass: 'rgba(255, 255, 255, 0.94)',
  text: '#2A1B4A',
  textMuted: '#6B5B85',
  textDim: '#9B8BB5',
  accent: '#6D4AFF',
  accentSoft: '#EDE5FF',
  accentGlow: 'rgba(109, 74, 255, 0.14)',
  accentDeep: '#4C2BB8',
  lavender: '#C4B0FF',
  indigo: '#3D2A6D',
  cyan: '#7EC8E8',
  cyanSoft: '#E8F6FC',
  onAccent: '#FFFFFF',
  mint: '#0D9488',
  mintSoft: '#CCFBF1',
  danger: '#DC2626',
  warning: '#D97706',
  border: '#E4DCF2',
  borderSoft: '#EFE8F8',
  input: '#F3EEFA',
  bubbleUser: '#6D4AFF',
  bubbleUserText: '#FFFFFF',
  bubbleAi: '#EDE5FF',
  bubbleAiText: '#2A1B4A',
  overlay: 'rgba(42, 27, 74, 0.42)',
  success: '#0D9488',
  banner: '#F3EEFA',
  bannerBorder: '#D4C6F0',
  progressTrack: '#E4DCF2',
  progressFill: '#C4B0FF',
} as const;

export type ColorName = keyof typeof colors;
