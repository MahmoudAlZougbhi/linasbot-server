import { Image, StyleSheet, Text, View } from 'react-native';

import { linasAssets } from '../features/linas/avatarAssets';
import { colors, fonts, typography } from '../theme';

type Props = {
  title: string;
  body?: string;
  showMascot?: boolean;
};

export function EmptyState({ title, body, showMascot = false }: Props) {
  return (
    <View style={styles.wrap}>
      {showMascot ? (
        <Image source={linasAssets.emptyState} style={styles.mascot} resizeMode="contain" />
      ) : null}
      <Text style={styles.title}>{title}</Text>
      {body ? <Text style={styles.body}>{body}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { paddingVertical: 40, paddingHorizontal: 28, alignItems: 'center' },
  mascot: { width: 160, height: 160, marginBottom: 12 },
  title: {
    ...typography.bodyStrong,
    fontFamily: fonts.bodyMedium,
    color: colors.text,
    textAlign: 'center',
  },
  body: {
    ...typography.caption,
    color: colors.textMuted,
    textAlign: 'center',
    marginTop: 8,
    maxWidth: 280,
  },
});
