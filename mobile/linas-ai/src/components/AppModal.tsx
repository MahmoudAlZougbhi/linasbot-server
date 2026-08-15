import type { ReactNode } from 'react';
import { Modal, type ModalProps } from 'react-native';

type Props = ModalProps & { children: ReactNode };

/**
 * Transparent modal shell with iOS overFullScreen so the host window does not
 * flash solid black behind semi-transparent scrims.
 */
export function AppModal({ children, transparent = true, ...rest }: Props) {
  return (
    <Modal
      transparent={transparent}
      statusBarTranslucent
      presentationStyle="overFullScreen"
      {...rest}
    >
      {children}
    </Modal>
  );
}
