import { StyleSheet, View } from 'react-native';

/** Soft fade below the status-bar wash — letters stay readable underneath. */
const TAIL = [0.28, 0.16, 0.09, 0.045, 0.02];
const STEP_H = 7;

function hexRgba(hex: string, alpha: number): string {
  const n = hex.replace('#', '');
  const full = n.length === 3 ? n.split('').map((c) => c + c).join('') : n;
  const r = parseInt(full.slice(0, 2), 16);
  const g = parseInt(full.slice(2, 4), 16);
  const b = parseInt(full.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

type Props = {
  insetTop: number;
  color: string;
};

/** Light translucent wash + fade. JS-only — no extra native module. */
export function ChatTopFade({ insetTop, color }: Props) {
  return (
    <View pointerEvents="none" style={[styles.wrap, { height: insetTop + TAIL.length * STEP_H }]}>
      <View style={{ height: insetTop, backgroundColor: hexRgba(color, 0.42) }} />
      {TAIL.map((alpha, i) => (
        <View key={i} style={{ height: STEP_H, backgroundColor: hexRgba(color, alpha) }} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
  },
});
