import { StyleSheet, Text, View, type ViewStyle } from 'react-native';

import { fonts, useTheme } from '../theme';

type Props = {
  size?: number;
  labeled?: boolean;
  label?: string;
  labelColor?: string;
  style?: ViewStyle;
};

/** Static Linas star micro-mark — never animated / never a character avatar. */
export function LinasStarMark({
  size = 22,
  labeled = false,
  label = 'Linas',
  labelColor,
  style,
}: Props) {
  const { colors } = useTheme();
  const titleColor = labelColor ?? colors.text;
  return (
    <View
      style={[styles.row, style]}
      accessibilityRole="image"
      accessibilityLabel={labeled ? label : 'Linas'}
    >
      <Text style={{ color: colors.accent, fontSize: size, lineHeight: size + 2 }}>✦</Text>
      {labeled ? (
        <Text
          style={[styles.label, { color: titleColor, fontSize: Math.max(15, size - 3) }]}
        >
          {label}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  label: { fontFamily: fonts.bodyMedium, fontWeight: '700' },
});
