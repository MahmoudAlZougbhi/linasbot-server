import { StyleSheet, Text, View, type ViewStyle } from 'react-native';

import { LinasSparkleIcon } from './LinasSparkleIcon';
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
      <LinasSparkleIcon size={size} color={colors.accent} />
      {labeled ? (
        <Text
          style={[
            styles.label,
            { color: titleColor, fontSize: size, lineHeight: size },
          ]}
        >
          {label}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  label: { fontFamily: fonts.bodyMedium, fontWeight: '700' },
});
