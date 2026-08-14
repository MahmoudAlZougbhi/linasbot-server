import type { ReactNode } from 'react';
import { useEffect, useRef, useState } from 'react';
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

import { radii, useTheme } from '../theme';

/** Keep in sync with close `Animated.timing` duration below (+ small buffer). */
const DRAWER_CLOSE_MS = 260;

type Props = {
  open: boolean;
  side: 'left' | 'right';
  onClose: () => void;
  children: ReactNode;
  widthRatio?: number;
  style?: ViewStyle;
};

export function SideDrawer({
  open,
  side,
  onClose,
  children,
  widthRatio = 0.82,
  style,
}: Props) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [screen, setScreen] = useState(() => Dimensions.get('window'));
  const width = Math.min(screen.width * widthRatio, 360);
  const height = screen.height;
  const closedX = side === 'left' ? -width : width;
  const anim = useRef(new Animated.Value(closedX)).current;
  const fade = useRef(new Animated.Value(0)).current;
  const [hitActive, setHitActive] = useState(open);

  useEffect(() => {
    const sub = Dimensions.addEventListener('change', ({ window }) => {
      setScreen(window);
    });
    return () => sub.remove();
  }, []);

  useEffect(() => {
    if (open) {
      setHitActive(true);
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
    if (!open) {
      const t = setTimeout(() => setHitActive(false), DRAWER_CLOSE_MS);
      return () => clearTimeout(t);
    }
  }, [open, anim, fade, closedX]);

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents={hitActive ? 'auto' : 'none'}>
      <Animated.View style={[styles.scrim, { opacity: fade, backgroundColor: colors.overlay }]}>
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />
      </Animated.View>
      <Animated.View
        style={[
          styles.panel,
          side === 'left' ? styles.left : styles.right,
          {
            width,
            height,
            paddingTop: insets.top + 8,
            paddingBottom: 0,
            transform: [{ translateX: anim }],
            backgroundColor: colors.surfaceGlass,
            borderColor: colors.border,
          },
          style,
        ]}
      >
        <View style={styles.body}>{children}</View>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  scrim: {
    ...StyleSheet.absoluteFill,
  },
  panel: {
    position: 'absolute',
    top: 0,
    paddingHorizontal: 16,
  },
  body: { flex: 1, minHeight: 0 },
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
