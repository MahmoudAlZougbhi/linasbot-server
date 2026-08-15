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
  ...rest
}: Props) {
  const resolvedAnimation = animationType === 'slide' ? 'fade' : animationType;

  return (
    <Modal
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
