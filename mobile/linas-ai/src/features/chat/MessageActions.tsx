import * as Clipboard from 'expo-clipboard';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, useTheme } from '../../theme';

type Props = {
  text: string;
  onRetry?: () => void;
};

export function MessageActions({ text, onRetry }: Props) {
  const { colors } = useTheme();
  return (
    <View style={styles.row}>
      <Pressable
        onPress={() => void Clipboard.setStringAsync(text)}
        accessibilityLabel="Copy message"
        hitSlop={8}
      >
        <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 12 }}>Copy</Text>
      </Pressable>
      {onRetry ? (
        <Pressable onPress={onRetry} accessibilityLabel="Retry" hitSlop={8}>
          <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 12 }}>Retry</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 16, marginTop: 4, marginLeft: 12 },
});
