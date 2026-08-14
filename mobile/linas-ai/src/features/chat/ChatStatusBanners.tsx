import { Pressable, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useI18n } from '../../i18n/LanguageContext';
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
  const { tr } = useI18n();
  const insets = useSafeAreaInsets();
  if (!offline && !errorLabel && !voiceError) return null;
  return (
    <View style={{ paddingTop: insets.top }}>
      {offline ? (
        <Text style={[styles.error, { color: colors.warning }]}>{tr('offlineDraftPreserved')}</Text>
      ) : null}
      {errorLabel ? (
        <Pressable onPress={onRetry}>
          <Text style={styles.error}>
            {errorLabel} · {tr('tapToRetry')}
          </Text>
        </Pressable>
      ) : null}
      {voiceError ? <Text style={styles.error}>{voiceError}</Text> : null}
    </View>
  );
}
