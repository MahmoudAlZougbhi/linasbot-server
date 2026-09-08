import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { HIT, fonts, useTheme } from '../../theme';

type Props = {
  count: number;
  active: boolean;
  onPress: () => void;
};

export function InboxHumanHeaderButton({ count, active, onPress }: Props) {
  const { colors } = useTheme();
  const badge = count > 99 ? '99+' : count > 0 ? String(count) : null;

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={
        active ? 'Show all conversations' : 'Show conversations waiting for a human'
      }
      accessibilityState={{ selected: active }}
      style={({ pressed }) => [styles.hit, pressed && styles.pressed]}
    >
      <AppIcon icon={feather('user')} size={22} color={active ? colors.accentDeep : colors.text} />
      {badge ? (
        <View style={[styles.badge, { backgroundColor: colors.accentDeep }]}>
          <Text style={[styles.badgeText, { color: colors.onAccent }]}>{badge}</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  hit: {
    width: HIT,
    height: HIT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pressed: { opacity: 0.55 },
  badge: {
    position: 'absolute',
    top: 6,
    right: 4,
    minWidth: 16,
    height: 16,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 4,
  },
  badgeText: { fontFamily: fonts.bodyMedium, fontSize: 10, lineHeight: 12, fontWeight: '700' },
});
