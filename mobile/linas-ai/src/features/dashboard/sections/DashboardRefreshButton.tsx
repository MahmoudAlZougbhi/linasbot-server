import { Ionicons } from '@expo/vector-icons';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { HIT, useTheme } from '../../../theme';

type Props = {
  onRefresh: () => void;
  refreshing: boolean;
};

export function DashboardRefreshButton({ onRefresh, refreshing }: Props) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onRefresh}
      disabled={refreshing}
      accessibilityRole="button"
      accessibilityLabel="Refresh dashboard"
      style={({ pressed }) => [
        styles.btn,
        { borderColor: colors.border, backgroundColor: colors.surface },
        pressed && styles.pressed,
      ]}
    >
      {refreshing ? (
        <ActivityIndicator size="small" color={colors.accent} />
      ) : (
        <Ionicons name="refresh" size={20} color={colors.text} />
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
    alignItems: 'center',
    justifyContent: 'center',
  },
  pressed: { opacity: 0.6 },
});
