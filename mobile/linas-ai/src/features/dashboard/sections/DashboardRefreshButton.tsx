import { Ionicons } from '@expo/vector-icons';
import { ActivityIndicator, Pressable, StyleSheet } from 'react-native';

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
      style={({ pressed }) => [styles.btn, pressed && styles.pressed]}
    >
      {refreshing ? (
        <ActivityIndicator size="small" color={colors.text} />
      ) : (
        <Ionicons name="refresh-outline" size={22} color={colors.text} />
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
    width: HIT,
    height: HIT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pressed: { opacity: 0.55 },
});
