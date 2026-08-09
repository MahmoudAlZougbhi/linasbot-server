import { Image, StyleSheet, Text, View, type ImageStyle, type ViewStyle } from 'react-native';

import { linasAssets } from '../features/linas/avatarAssets';
import { colors, fonts, typography } from '../theme';

type Props = {
  size?: 'sm' | 'md' | 'lg';
  showWordmark?: boolean;
  showMark?: boolean;
  tagline?: string;
  style?: ViewStyle;
};

const SIZES = { sm: 40, md: 64, lg: 96 } as const;

export function BrandMark({
  size = 'md',
  showWordmark = false,
  showMark = true,
  tagline = 'Think it. Ask it. Linas has it.',
  style,
}: Props) {
  const dim = SIZES[size];
  const imageStyle: ImageStyle = { width: dim, height: dim, borderRadius: dim / 2 };
  return (
    <View style={[styles.col, style]}>
      {showMark ? (
        <View style={[styles.ring, { width: dim + 8, height: dim + 8, borderRadius: (dim + 8) / 2 }]}>
          <Image source={linasAssets.icon} style={imageStyle} />
        </View>
      ) : null}
      {showWordmark ? (
        <View style={styles.copy}>
          <Text style={styles.word}>Linas AI</Text>
          <Text style={styles.tag}>{tagline}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  col: { alignItems: 'center', gap: 12 },
  ring: {
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accentSoft,
    borderWidth: 1,
    borderColor: colors.border,
  },
  copy: { alignItems: 'center' },
  word: {
    ...typography.title,
    color: colors.accentDeep,
    fontFamily: fonts.display,
    fontSize: 30,
    textAlign: 'center',
  },
  tag: {
    ...typography.caption,
    color: colors.textMuted,
    marginTop: 4,
    textAlign: 'center',
  },
});
