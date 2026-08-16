import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

type Props = {
  children: ReactNode;
};

/**
 * Full-screen overlay for routes that stack above keep-mounted module panes
 * (cm_section, products, services, …). Without absolute positioning the pane
 * underneath can still capture layout/touches on some devices.
 */
export function EphemeralRoute({ children }: Props) {
  return <View style={styles.root}>{children}</View>;
}

const styles = StyleSheet.create({
  root: {
    ...StyleSheet.absoluteFill,
    zIndex: 2,
    elevation: 2,
  },
});
