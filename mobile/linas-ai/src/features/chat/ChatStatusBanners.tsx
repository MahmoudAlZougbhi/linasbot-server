import { Pressable, Text } from 'react-native';

import { useTheme } from '../../theme';
import { chatScreenStyles as styles } from './chatScreenStyles';

type Props = {
  offline: boolean;
  errorLabel: string | null;
  voiceError: string | null;
  onRetry: () => void;
};

export function ChatStatusBanners({ offline, errorLabel, voiceError, onRetry }: Props) {
  const { colors } = useTheme();
  return (
    <>
      {offline ? (
        <Text style={[styles.error, { color: colors.warning }]}>
          Offline — your draft is preserved. Retry when connected.
        </Text>
      ) : null}
      {errorLabel ? (
        <Pressable onPress={onRetry}>
          <Text style={styles.error}>
            {errorLabel} · Tap to retry
          </Text>
        </Pressable>
      ) : null}
      {voiceError ? <Text style={styles.error}>{voiceError}</Text> : null}
    </>
  );
}
