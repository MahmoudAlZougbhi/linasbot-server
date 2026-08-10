import type { ReactNode } from 'react';
import { useEffect, useRef } from 'react';
import {
  Animated,
  Dimensions,
  Keyboard,
  Pressable,
  StyleSheet,
  View,
  type ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, radii } from '../theme';

type Props = {
  open: boolean;
  side: 'left' | 'right';
  onClose: () => void;
  children: ReactNode;
  widthRatio?: number;
  style?: ViewStyle;
};

const SCREEN_W = Dimensions.get('window').width;

export function SideDrawer({
  open,
  side,
  onClose,
  children,
  widthRatio = 0.82,
  style,
}: Props) {
  const insets = useSafeAreaInsets();
  const width = Math.min(SCREEN_W * widthRatio, 360);
  const closedX = side === 'left' ? -width : width;
  const anim = useRef(new Animated.Value(closedX)).current;
  const fade = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (open) {
      Keyboard.dismiss();
    }
    Animated.parallel([
      Animated.timing(anim, {
        toValue: open ? 0 : closedX,
        duration: 240,
        useNativeDriver: true,
      }),
      Animated.timing(fade, {
        toValue: open ? 1 : 0,
        duration: 220,
        useNativeDriver: true,
      }),
    ]).start();
  }, [open, anim, fade, closedX]);

  if (!open) {
    // Keep mounted briefly for close animation — still render when animating out.
  }

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents={open ? 'auto' : 'none'}>
      <Animated.View style={[styles.scrim, { opacity: fade }]}>
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />
      </Animated.View>
      <Animated.View
        style={[
          styles.panel,
          side === 'left' ? styles.left : styles.right,
          {
            width,
            paddingTop: insets.top + 8,
            paddingBottom: insets.bottom + 12,
            transform: [{ translateX: anim }],
          },
          style,
        ]}
      >
        {children}
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  scrim: {
    ...StyleSheet.absoluteFill,
    backgroundColor: colors.overlay,
  },
  panel: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    backgroundColor: colors.surfaceGlass,
    borderColor: colors.border,
    paddingHorizontal: 16,
  },
  left: {
    left: 0,
    borderRightWidth: 1,
    borderTopRightRadius: radii.lg,
    borderBottomRightRadius: radii.lg,
  },
  right: {
    right: 0,
    borderLeftWidth: 1,
    borderTopLeftRadius: radii.lg,
    borderBottomLeftRadius: radii.lg,
  },
});
