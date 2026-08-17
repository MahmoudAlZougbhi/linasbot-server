import { useRef, type ReactNode } from 'react';
import { Animated, PanResponder, Pressable, StyleSheet, Text, View } from 'react-native';

const REVEAL = 88;
const TEAL_DELETE = '#DC2626';

type Props = {
  enabled?: boolean;
  deleteLabel: string;
  onRequestDelete: () => void;
  children: ReactNode;
};

/** Swipe left or long-press to ask for Delete. Parent must confirm before removing. */
export function AiSetupDeletableRow({
  enabled = true,
  deleteLabel,
  onRequestDelete,
  children,
}: Props) {
  const tx = useRef(new Animated.Value(0)).current;
  const startX = useRef(0);

  const pan = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, g) =>
        enabled && Math.abs(g.dx) > 10 && Math.abs(g.dx) > Math.abs(g.dy) * 1.2,
      onPanResponderGrant: () => {
        tx.stopAnimation((value) => {
          startX.current = value;
        });
      },
      onPanResponderMove: (_, g) => {
        const next = Math.min(0, Math.max(-REVEAL, startX.current + g.dx));
        tx.setValue(next);
      },
      onPanResponderRelease: (_, g) => {
        const shouldOpen = startX.current + g.dx < -REVEAL / 2 || g.vx < -0.45;
        Animated.spring(tx, {
          toValue: shouldOpen ? -REVEAL : 0,
          useNativeDriver: true,
          bounciness: 0,
        }).start();
      },
    }),
  ).current;

  if (!enabled) return <>{children}</>;

  return (
    <View style={styles.clip}>
      <View style={styles.behind}>
        <Pressable
          onPress={onRequestDelete}
          accessibilityRole="button"
          accessibilityLabel={deleteLabel}
          style={styles.deleteBtn}
        >
          <Text style={styles.deleteText}>{deleteLabel}</Text>
        </Pressable>
      </View>
      <Animated.View
        style={[styles.front, { transform: [{ translateX: tx }] }]}
        {...pan.panHandlers}
      >
        {children}
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  clip: { overflow: 'hidden', borderRadius: 12 },
  behind: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'flex-end',
    justifyContent: 'center',
    backgroundColor: TEAL_DELETE,
  },
  deleteBtn: {
    width: REVEAL,
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
  deleteText: { color: '#FFFFFF', fontSize: 14, fontWeight: '700' },
  front: { backgroundColor: 'transparent' },
});
