/**
 * Static star mark wrapper — BrandMark must never render a mascot/character.
 */
import { StyleSheet, Text, View, type ViewStyle } from 'react-native';

import { LinasStarMark } from './LinasStarMark';
import { fonts, typography, useTheme } from '../theme';

type Props = {
  size?: 'sm' | 'md' | 'lg';
  showWordmark?: boolean;
  showMark?: boolean;
  tagline?: string;
  style?: ViewStyle;
};

const SIZES = { sm: 28, md: 48, lg: 72 } as const;

export function BrandMark({
  size = 'md',
  showWordmark = false,
  showMark = true,
  tagline = 'Think it. Ask it. Linas has it.',
  style,
}: Props) {
  const { colors } = useTheme();
  const dim = SIZES[size];
  return (
    <View style={[styles.col, style]}>
      {showMark ? <LinasStarMark size={dim} /> : null}
      {showWordmark ? (
        <View style={styles.copy}>
          <Text style={[styles.word, { color: colors.accentDeep }]}>Linas AI</Text>
          <Text style={[styles.tag, { color: colors.textMuted }]}>{tagline}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  col: { alignItems: 'center', gap: 12 },
  copy: { alignItems: 'center' },
  word: {
    ...typography.title,
    fontFamily: fonts.display,
    fontSize: 30,
    textAlign: 'center',
  },
  tag: {
    ...typography.caption,
    marginTop: 4,
    textAlign: 'center',
  },
});
