import { StyleSheet, Text, View } from 'react-native';

import { StatusChip } from '../../components/StatusChip';
import { colors, fonts, radii, spacing } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';

type Props = { onBack: () => void };

/** Truthful: Meta comments not live-verified in production bindings. */
export function CommentsScreen({ onBack }: Props) {
  return (
    <ScreenChrome title="Comments" subtitle="Social comment automation" onBack={onBack}>
      <View style={styles.card}>
        <StatusChip label="Coming later" tone="soon" />
        <Text style={styles.title}>Not enabled</Text>
        <Text style={styles.body}>
          Comment replies are not live-verified on current Meta production bindings. Linas AI
          processes private messages (Messenger / Instagram DMs). This screen will unlock when
          comments are capability-verified — no fake toggle.
        </Text>
      </View>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    padding: spacing.xl,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.md,
  },
  title: { color: colors.text, fontFamily: fonts.display, fontSize: 20 },
  body: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 14, lineHeight: 21 },
});
