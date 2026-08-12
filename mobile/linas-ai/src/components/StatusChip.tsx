import { StyleSheet, Text, View } from 'react-native';

import { fonts, radii, spacing, useTheme, type ThemeColors } from '../theme';

type Tone = 'neutral' | 'ok' | 'warn' | 'soon';

type Props = {
  label: string;
  tone?: Tone;
};

function toneColors(colors: ThemeColors, tone: Tone): { bg: string; fg: string } {
  switch (tone) {
    case 'ok':
      return { bg: colors.mintSoft, fg: colors.mint };
    case 'warn':
      return { bg: colors.accentSoft, fg: colors.warning };
    case 'soon':
      return { bg: colors.surfaceAlt, fg: colors.textDim };
    case 'neutral':
    default:
      return { bg: colors.surfaceAlt, fg: colors.textMuted };
  }
}

export function StatusChip({ label, tone = 'neutral' }: Props) {
  const { colors } = useTheme();
  const t = toneColors(colors, tone);
  return (
    <View style={[styles.chip, { backgroundColor: t.bg }]}>
      <Text style={[styles.text, { color: t.fg }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    alignSelf: 'flex-start',
    borderRadius: radii.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
  },
  text: { fontFamily: fonts.bodyMedium, fontSize: 12 },
});
