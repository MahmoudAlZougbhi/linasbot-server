import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, radii, useTheme } from '../../theme';

type Props = {
  visible: boolean;
  onPress: () => void;
};

/** ChatGPT-style jump control — centered above the composer. */
export function ScrollToLatestFab({ visible, onPress }: Props) {
  const { colors } = useTheme();
  if (!visible) return null;
  return (
    <View pointerEvents="box-none" style={styles.wrap}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Scroll to latest messages"
        onPress={onPress}
        style={({ pressed }) => [
          styles.btn,
          {
            backgroundColor: colors.bgElevated,
            borderColor: colors.border,
            opacity: pressed ? 0.85 : 1,
          },
        ]}
      >
        <Text style={[styles.arrow, { color: colors.text }]}>↓</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 12,
    alignItems: 'center',
  },
  btn: {
    width: 40,
    height: 40,
    borderRadius: radii.pill,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.12,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 3,
  },
  arrow: { fontFamily: fonts.bodyMedium, fontSize: 18, fontWeight: '700', marginTop: -1 },
});
