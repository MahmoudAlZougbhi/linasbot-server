import { StyleSheet, Text, View } from 'react-native';

import { colors, fonts, radii, spacing } from '../theme';

type Tone = 'neutral' | 'ok' | 'warn' | 'soon';

type Props = {
  label: string;
  tone?: Tone;
};

const TONE: Record<Tone, { bg: string; fg: string }> = {
  neutral: { bg: colors.surfaceAlt, fg: colors.textMuted },
  ok: { bg: colors.mintSoft, fg: colors.mint },
  warn: { bg: colors.accentSoft, fg: colors.warning },
  soon: { bg: colors.surfaceAlt, fg: colors.textDim },
};

export function StatusChip({ label, tone = 'neutral' }: Props) {
  const t = TONE[tone];
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
