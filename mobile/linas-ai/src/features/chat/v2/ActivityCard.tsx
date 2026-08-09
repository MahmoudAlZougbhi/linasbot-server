import { StyleSheet, Text, View } from 'react-native';

import { colors, fonts, radii, spacing } from '../../../theme';
import type { StreamCard } from './useOwnerStream';

type Props = { card: StreamCard };

export function ActivityCard({ card }: Props) {
  return (
    <View style={styles.card} accessibilityLabel={`${card.kind} card: ${card.title}`}>
      <Text style={styles.kind}>{card.kind}</Text>
      <Text style={styles.title}>{card.title}</Text>
      {card.body ? <Text style={styles.body}>{card.body}</Text> : null}
      {card.status ? <Text style={styles.status}>{card.status}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
    padding: spacing.md,
    borderRadius: radii.md,
    backgroundColor: colors.bgElevated,
    borderWidth: 1,
    borderColor: colors.border,
  },
  kind: {
    color: colors.textDim,
    fontFamily: fonts.bodyMedium,
    fontSize: 11,
    textTransform: 'uppercase',
    marginBottom: 4,
  },
  title: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 15 },
  body: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 13, marginTop: 4 },
  status: { color: colors.accent, fontFamily: fonts.body, fontSize: 12, marginTop: 6 },
});
