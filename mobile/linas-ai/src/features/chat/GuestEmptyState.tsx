import { Pressable, StyleSheet, Text, View } from 'react-native';

import { LinasStarMark } from '../../components/LinasStarMark';
import { fonts, radii, spacing, useTheme } from '../../theme';

export const GUEST_STARTERS = [
  {
    id: 'what',
    title: 'What can Linas AI do?',
    subtitle: 'Learn the owner copilot and scope.',
    prompt: 'What can Linas AI do for my business?',
  },
  {
    id: 'dm',
    title: 'How are DMs and comments handled?',
    subtitle: 'See the safe reply and audit workflow.',
    prompt: 'How does Linas handle social media DMs and comments?',
  },
  {
    id: 'connect',
    title: 'How do I connect my business?',
    subtitle: 'Learn the steps before signing in.',
    prompt: 'How do I connect my business after I sign in?',
  },
] as const;

type Props = {
  onPick: (prompt: string) => void;
};

export function GuestEmptyState({ onPick }: Props) {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap}>
      <LinasStarMark size={42} />
      <Text style={[styles.title, { color: colors.text }]}>How can Linas help?</Text>
      <Text style={[styles.body, { color: colors.textMuted }]}>
        Ask what Linas does, how customer replies work, or how to get started after sign-in.
      </Text>
      <View style={styles.cards}>
        {GUEST_STARTERS.map((s) => (
          <Pressable
            key={s.id}
            style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}
            onPress={() => onPick(s.prompt)}
            accessibilityLabel={s.title}
            accessibilityRole="button"
          >
            <View style={{ flex: 1 }}>
              <Text style={[styles.cardTitle, { color: colors.text }]}>{s.title}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 12 }}>{s.subtitle}</Text>
            </View>
            <Text style={{ color: colors.textDim }}>›</Text>
          </Pressable>
        ))}
      </View>
      <Text style={[styles.hint, { color: colors.textDim }]}>
        Guest access · Try Linas now. Sign in to save Owner work.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { paddingVertical: 28, paddingHorizontal: 20, alignItems: 'center' },
  title: {
    fontFamily: fonts.display,
    fontSize: 26,
    marginTop: spacing.lg,
    textAlign: 'center',
  },
  body: {
    fontFamily: fonts.body,
    fontSize: 14,
    textAlign: 'center',
    marginTop: spacing.sm,
    maxWidth: 320,
  },
  cards: { width: '100%', gap: 10, marginTop: spacing.xl },
  card: {
    minHeight: 64,
    borderRadius: radii.lg,
    borderWidth: 1,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  cardTitle: { fontFamily: fonts.bodyMedium, fontSize: 15 },
  hint: { marginTop: spacing.lg, fontSize: 12, textAlign: 'center' },
});
