import { Image, StyleSheet, Text, View, type ImageStyle, type ViewStyle } from 'react-native';

import { colors, fonts, typography } from '../theme';

type Props = {
  size?: 'sm' | 'md' | 'lg';
  showWordmark?: boolean;
  style?: ViewStyle;
};

const SIZES = { sm: 36, md: 56, lg: 88 } as const;

export function BrandMark({ size = 'md', showWordmark = false, style }: Props) {
  const dim = SIZES[size];
  const imageStyle: ImageStyle = { width: dim, height: dim, borderRadius: dim * 0.28 };
  return (
    <View style={[styles.row, style]}>
      <View style={[styles.ring, { width: dim + 8, height: dim + 8, borderRadius: (dim + 8) * 0.3 }]}>
        <Image source={require('../../assets/icon.png')} style={imageStyle} />
      </View>
      {showWordmark ? (
        <View>
          <Text style={styles.word}>Linas AI</Text>
          <Text style={styles.tag}>Business AI, calmly powerful</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  ring: {
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accentGlow,
    borderWidth: 1,
    borderColor: colors.border,
  },
  word: { ...typography.title, color: colors.text, fontFamily: fonts.display, fontSize: 28 },
  tag: { ...typography.caption, color: colors.textMuted, marginTop: 2 },
});
