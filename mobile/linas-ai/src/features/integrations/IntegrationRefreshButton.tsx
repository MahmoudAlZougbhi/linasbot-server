import { ActivityIndicator, Pressable, StyleSheet } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { HIT, colors } from '../../theme';

type Props = {
  onRefresh: () => void;
  refreshing: boolean;
  accessibilityLabel: string;
};

/** Circular header refresh matching the Integrations handoff. */
export function IntegrationRefreshButton({ onRefresh, refreshing, accessibilityLabel }: Props) {
  return (
    <Pressable
      onPress={onRefresh}
      disabled={refreshing}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      style={({ pressed }) => [styles.btn, pressed && styles.pressed]}
    >
      {refreshing ? (
        <ActivityIndicator size="small" color={colors.accent} />
      ) : (
        <AppIcon icon={feather('refresh-cw')} size={18} color={colors.text} />
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
    width: HIT - 8,
    height: HIT - 8,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pressed: { opacity: 0.6 },
});
