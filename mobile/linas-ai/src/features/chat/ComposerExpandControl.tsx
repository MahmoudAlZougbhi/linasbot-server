import { Pressable, StyleSheet, View } from 'react-native';

type Props = {
  expanded: boolean;
  onPress: () => void;
  backgroundColor: string;
  iconColor: string;
  accessibilityLabel: string;
};

function Corner({
  color,
  top,
  left,
  right,
  bottom,
}: {
  color: string;
  top?: number;
  left?: number;
  right?: number;
  bottom?: number;
}) {
  return (
    <View
      style={{
        position: 'absolute',
        width: 5,
        height: 5,
        top,
        left,
        right,
        bottom,
        borderColor: color,
        borderTopWidth: top != null ? 1.55 : 0,
        borderBottomWidth: bottom != null ? 1.55 : 0,
        borderLeftWidth: left != null ? 1.55 : 0,
        borderRightWidth: right != null ? 1.55 : 0,
      }}
    />
  );
}

/** Four L-brackets: outward = expand, inward = collapse. */
function CornersGlyph({ color, inward }: { color: string; inward: boolean }) {
  const e = inward ? 3 : 0;
  return (
    <View style={{ width: 14, height: 14 }}>
      <Corner color={color} top={e} left={e} />
      <Corner color={color} top={e} right={e} />
      <Corner color={color} bottom={e} left={e} />
      <Corner color={color} bottom={e} right={e} />
    </View>
  );
}

/** Gray circle, top-right of the pill / expanded sheet. */
export function ComposerExpandControl({
  expanded,
  onPress,
  backgroundColor,
  iconColor,
  accessibilityLabel,
}: Props) {
  return (
    <Pressable
      onPress={onPress}
      style={[styles.hit, { backgroundColor }]}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      hitSlop={6}
    >
      <CornersGlyph color={iconColor} inward={expanded} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  hit: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
