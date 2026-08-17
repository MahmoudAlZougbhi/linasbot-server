import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../../components/AppIcon';
import { fonts } from '../../../theme';
import {
  AB_BORDER,
  AB_FOREST,
  AB_MUTED,
  AB_RADIUS,
  AB_TEAL,
  AB_TEAL_SOFT,
  AB_TEXT,
} from './aiBasicsChrome';
import type { GreetingRule } from './aiBasicsModel';

type Props = {
  item: GreetingRule;
  untitled: string;
  activeLabel: string;
  onPress: () => void;
  onLongPress?: () => void;
};

export function GreetingCard({ item, untitled, activeLabel, onPress, onLongPress }: Props) {
  const title = item.name.trim() || untitled;
  const subtitle = item.notes.trim() || item.en.trim();
  return (
    <Pressable
      onPress={onPress}
      onLongPress={onLongPress}
      delayLongPress={380}
      accessibilityRole="button"
      accessibilityLabel={title}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}
    >
      <View style={styles.iconSq}>
        <AppIcon icon={feather('message-circle')} size={20} color={AB_TEAL} />
      </View>
      <View style={styles.copy}>
        <Text style={styles.title} numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? (
          <Text style={styles.sub} numberOfLines={2}>
            {subtitle}
          </Text>
        ) : null}
        {item.enabled ? (
          <View style={styles.badge}>
            <View style={styles.dot} />
            <Text style={styles.badgeText}>{activeLabel}</Text>
          </View>
        ) : null}
      </View>
      <AppIcon icon={feather('chevron-right')} size={18} color={AB_MUTED} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: AB_BORDER,
    borderRadius: AB_RADIUS,
    padding: 14,
  },
  pressed: { opacity: 0.72 },
  iconSq: {
    width: 44,
    height: 44,
    borderRadius: 10,
    backgroundColor: AB_TEAL_SOFT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  copy: { flex: 1, gap: 4 },
  title: { color: AB_TEXT, fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
  sub: { color: AB_MUTED, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  badge: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2 },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: AB_FOREST },
  badgeText: { color: AB_FOREST, fontFamily: fonts.bodyMedium, fontSize: 12, fontWeight: '600' },
});
