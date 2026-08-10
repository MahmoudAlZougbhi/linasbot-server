import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { GradientBackground } from '../../components/GradientBackground';
import { LinasStarMark } from '../../components/LinasStarMark';
import { fonts, radii, spacing, useTheme } from '../../theme';

type Props = {
  loading?: boolean;
  note?: string | null;
  onOpenSubscription: () => void;
  onRefresh: () => void;
  onLogout: () => void;
};

/** Blocks authenticated app use until entitlement is active/trial/grace. */
export function SubscriptionGateScreen({
  loading,
  note,
  onOpenSubscription,
  onRefresh,
  onLogout,
}: Props) {
  const { colors } = useTheme();
  return (
    <GradientBackground>
      <View style={styles.wrap}>
        <LinasStarMark size={48} />
        <Text style={[styles.title, { color: colors.text }]}>Subscribe to continue</Text>
        <Text style={[styles.body, { color: colors.textMuted }]}>
          New accounts need an active plan before Owner chat, Content Management, and integrations unlock.
          Guest mode still works without signing in.
        </Text>
        {note ? <Text style={[styles.note, { color: colors.textDim }]}>{note}</Text> : null}
        {loading ? <ActivityIndicator color={colors.accent} /> : null}
        <Pressable
          style={[styles.btn, { backgroundColor: colors.accent }]}
          onPress={onOpenSubscription}
          accessibilityRole="button"
          accessibilityLabel="Open subscription"
        >
          <Text style={styles.btnText}>View plans</Text>
        </Pressable>
        <Pressable
          style={[styles.btnGhost, { borderColor: colors.border }]}
          onPress={onRefresh}
          accessibilityRole="button"
          accessibilityLabel="Refresh subscription status"
        >
          <Text style={{ color: colors.text, fontFamily: fonts.bodyMedium }}>
            I already subscribed — refresh
          </Text>
        </Pressable>
        <Pressable onPress={onLogout} accessibilityRole="button">
          <Text style={{ color: colors.textDim, marginTop: spacing.md }}>Sign out</Text>
        </Pressable>
      </View>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    gap: spacing.md,
  },
  title: { fontFamily: fonts.display, fontSize: 24, textAlign: 'center', marginTop: spacing.md },
  body: { fontFamily: fonts.body, fontSize: 14, textAlign: 'center', maxWidth: 340 },
  note: { fontFamily: fonts.body, fontSize: 12, textAlign: 'center', maxWidth: 340 },
  btn: {
    marginTop: spacing.md,
    minHeight: 48,
    borderRadius: radii.md,
    paddingHorizontal: 28,
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'stretch',
  },
  btnText: { color: '#fff', fontFamily: fonts.bodyMedium, fontSize: 16 },
  btnGhost: {
    minHeight: 44,
    borderRadius: radii.md,
    borderWidth: 1,
    paddingHorizontal: 16,
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'stretch',
  },
});
