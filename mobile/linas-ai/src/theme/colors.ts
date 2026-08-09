/**
 * Soft futuristic Linas palette — aligned to the electric-blue mark.
 * Not pure black, not plain white, not neon spam.
 */
export const colors = {
  bg: '#0C1424',
  bgElevated: '#101A2E',
  surface: '#162033',
  surfaceAlt: '#1C2A42',
  surfaceGlass: 'rgba(22, 32, 51, 0.92)',
  text: '#E8EEF8',
  textMuted: '#8B9BB8',
  textDim: '#5E6E8A',
  accent: '#3B8EF0',
  accentSoft: '#1A4A7A',
  accentGlow: 'rgba(59, 142, 240, 0.22)',
  mint: '#5EE0B5',
  mintSoft: '#1F5C4A',
  danger: '#F07178',
  warning: '#E8C468',
  border: '#243248',
  borderSoft: '#1A2740',
  input: '#0F1828',
  bubbleUser: '#1E4D8C',
  bubbleAi: '#1A2438',
  overlay: 'rgba(6, 10, 18, 0.55)',
  success: '#5EE0B5',
} as const;

export type ColorName = keyof typeof colors;
