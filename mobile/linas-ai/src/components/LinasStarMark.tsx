import { StyleSheet, Text, View, type ViewStyle } from 'react-native';

import { LinasSparkleIcon } from './LinasSparkleIcon';
import { fonts, useTheme } from '../theme';

type Props = {
  size?: number;
  labeled?: boolean;
  label?: string;
  labelColor?: string;
  /** Name size when labeled. Sparkle stays `size` so the mark can be slightly larger. */
  labelSize?: number;
  style?: ViewStyle;
};

/** Static Linas star micro-mark — never animated / never a character avatar. */
export function LinasStarMark({
  size = 22,
  labeled = false,
  label = 'Linas',
  labelColor,
  labelSize,
  style,
}: Props) {
  const { colors } = useTheme();
  const titleColor = labelColor ?? colors.text;
  const nameSize = labelSize ?? size;
  const nameLineHeight = Math.ceil(nameSize * 1.4);
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
            { color: titleColor, fontSize: nameSize, lineHeight: nameLineHeight },
          ]}
        >
          {label}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    direction: 'ltr',
    overflow: 'visible',
  },
  label: { fontFamily: fonts.bodyMedium, fontWeight: '700' },
});
