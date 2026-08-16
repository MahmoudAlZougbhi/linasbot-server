import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather, mci } from '../../../components/AppIcon';
import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import {
  RQ_BORDER,
  RQ_ICON_SQ,
  RQ_MUTED,
  RQ_RADIUS,
  RQ_TEAL,
  RQ_TEAL_DARK,
  RQ_TEAL_SOFT,
} from './requestRuleChrome';
import {
  collectsPhrase,
  isGraphPublished,
  typeLabelKey,
  type RequestGraphRow,
  type RequestRuleItem,
} from './requestRuleModel';

type Props = {
  item: RequestRuleItem;
  graph?: RequestGraphRow;
  untitled: string;
  onPress: () => void;
  tr: (key: StringKey) => string;
};

export function RequestRuleCard({ item, graph, untitled, onPress, tr }: Props) {
  const published = isGraphPublished(graph);
  const collects = collectsPhrase(graph, tr('requestRulesCollectsEmpty'));
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={item.name || untitled}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}
    >
      <View style={styles.top}>
        <View style={styles.iconSq}>
          <AppIcon icon={mci('clipboard-text-outline')} size={20} color={RQ_TEAL} />
        </View>
        <View style={styles.copy}>
          <Text style={styles.title} numberOfLines={1}>
            {item.name.trim() || untitled}
          </Text>
          <Text style={styles.meta}>{tr(typeLabelKey(item.type))}</Text>
        </View>
        <AppIcon icon={feather('chevron-right')} size={18} color={RQ_MUTED} />
      </View>
      <View style={styles.divider} />
      <View style={styles.foot}>
        <View style={styles.footLeft}>
          <AppIcon icon={mci('clipboard-text-outline')} size={12} color={RQ_TEAL} />
          <Text style={styles.footText} numberOfLines={1}>
            {collects === tr('requestRulesCollectsEmpty')
              ? collects
              : tr('requestRulesCollects').replace('{fields}', collects)}
          </Text>
        </View>
        <Text style={styles.status}>
          {published ? tr('requestRulesPublished') : tr('requestRulesDraft')}
        </Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderColor: RQ_BORDER,
    borderWidth: 1,
    borderRadius: RQ_RADIUS,
    padding: 14,
    gap: 10,
  },
  pressed: { opacity: 0.7 },
  top: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  iconSq: {
    width: RQ_ICON_SQ,
    height: RQ_ICON_SQ,
    borderRadius: 10,
    backgroundColor: RQ_TEAL_SOFT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  copy: { flex: 1, gap: 4 },
  title: {
    color: RQ_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
    fontWeight: '700',
  },
  meta: { color: RQ_MUTED, fontFamily: fonts.body, fontSize: 13 },
  divider: { height: StyleSheet.hairlineWidth, backgroundColor: RQ_BORDER },
  foot: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  footLeft: { flexDirection: 'row', alignItems: 'center', gap: 6, flex: 1 },
  footText: { color: RQ_MUTED, fontFamily: fonts.body, fontSize: 12, flex: 1 },
  status: { color: RQ_MUTED, fontFamily: fonts.body, fontSize: 12 },
});
