import type { ReactNode } from 'react';
import { Modal, StyleSheet, View, type ModalProps } from 'react-native';

type Props = ModalProps & { children: ReactNode };

/**
 * Transparent modal shell with iOS overFullScreen so the host window does not
 * flash solid black behind semi-transparent scrims.
 *
 * Slide is remapped to fade: RN's slide animation moves the whole modal window
 * up from the bottom, exposing the opaque black host underneath (black bar flash).
 */
export function AppModal({
  children,
  transparent = true,
  animationType = 'fade',
  visible = false,
  ...rest
}: Props) {
  // A hidden RN Modal stays a native window on iOS and swallows every tap
  // until the process is killed. Chat keeps AuthGate and the + menu mounted.
  if (!visible) return null;
  const resolvedAnimation = animationType === 'slide' ? 'fade' : animationType;

  return (
    <Modal
      visible
      transparent={transparent}
      statusBarTranslucent
      presentationStyle="overFullScreen"
      animationType={resolvedAnimation}
      {...rest}
    >
      <View style={styles.host}>{children}</View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  host: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'transparent',
  },
});
