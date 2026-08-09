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
  const imageStyle: ImageStyle = { width: dim, height: dim, borderRadius: dim * 0.22 };
  return (
    <View style={[styles.row, style]}>
      <View style={[styles.ring, { width: dim + 6, height: dim + 6, borderRadius: (dim + 6) * 0.26 }]}>
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
    backgroundColor: colors.accentSoft,
    borderWidth: 1,
    borderColor: colors.border,
  },
  word: { ...typography.title, color: colors.text, fontFamily: fonts.display, fontSize: 28 },
  tag: { ...typography.caption, color: colors.textMuted, marginTop: 2 },
});
