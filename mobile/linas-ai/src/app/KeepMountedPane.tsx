import { useEffect, useState, type ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

type Props = {
  /** When true, pane is visible and interactive. */
  active: boolean;
  children: ReactNode;
};

/**
 * Mount children on first activation, then hide with `display: 'none'` instead of
 * unmounting. Preserves React state / avoids refetch spinners while navigating
 * within the app. Remount by changing the React `key` (e.g. auth epoch).
 */
export function KeepMountedPane({ active, children }: Props) {
  const [mounted, setMounted] = useState(active);

  useEffect(() => {
    if (active) setMounted(true);
  }, [active]);

  if (!mounted) return null;

  return (
    <View
      style={active ? styles.active : styles.inactive}
      pointerEvents={active ? 'auto' : 'none'}
      accessibilityElementsHidden={!active}
      importantForAccessibility={active ? 'auto' : 'no-hide-descendants'}
      collapsable={false}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  active: {
    ...StyleSheet.absoluteFill,
  },
  inactive: {
    ...StyleSheet.absoluteFill,
    display: 'none',
  },
});