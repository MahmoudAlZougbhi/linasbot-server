import { StyleSheet, Text, View } from 'react-native';

import { colors, fonts, typography } from '../theme';

type Props = {
  title: string;
  body?: string;
};

export function EmptyState({ title, body }: Props) {
  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>{title}</Text>
      {body ? <Text style={styles.body}>{body}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { paddingVertical: 48, paddingHorizontal: 28, alignItems: 'center' },
  title: { ...typography.bodyStrong, fontFamily: fonts.bodyMedium, color: colors.text, textAlign: 'center' },
  body: {
    ...typography.caption,
    color: colors.textMuted,
    textAlign: 'center',
    marginTop: 8,
    maxWidth: 280,
  },
});
