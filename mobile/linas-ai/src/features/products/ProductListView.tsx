import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import type { StringKey } from '../../i18n';
import { fonts } from '../../theme';
import { AiSetupListHeader } from '../cm/AiSetupListHeader';
import { AI_SETUP_TEAL } from '../cm/aiSetupDesign';
import type { Product } from './productsApi';

const INK = '#000000';
const MUTED = '#94A3B8';
const BORDER = '#E2E8F0';
const SOFT = '#E6F3F2';

type Props = {
  items: Product[];
  query: string;
  onQueryChange: (value: string) => void;
  onAdd: () => void;
  onImport: () => void;
  onSelect: (id: string) => void;
  tr: (key: StringKey) => string;
};

export function ProductListView({
  items,
  query,
  onQueryChange,
  onAdd,
  onImport,
  onSelect,
  tr,
}: Props) {
  const q = query.trim().toLowerCase();
  const visible = q ? items.filter((item) => item.name.toLowerCase().includes(q)) : items;
  const countLabel =
    visible.length === 1 ? `1 ${tr('productsCountOne')}` : `${visible.length} ${tr('productsCount')}`;

  return (
    <View style={styles.wrap}>
      <AiSetupListHeader
        query={query}
        onQueryChange={onQueryChange}
        searchPlaceholder={tr('productsSearch')}
        addA11yLabel={tr('productsAdd')}
        onAdd={onAdd}
        countLabel={countLabel}
      />
      <Pressable onPress={onImport} accessibilityRole="button" accessibilityLabel={tr('productsImport')}>
        <Text style={styles.import}>{tr('productsImport')}</Text>
      </Pressable>
      {visible.length === 0 ? <Text style={styles.empty}>{tr('productsEmpty')}</Text> : null}
      {visible.map((item) => (
        <Pressable
          key={item.id}
          onPress={() => onSelect(item.id)}
          accessibilityRole="button"
          accessibilityLabel={item.name}
          style={({ pressed }) => [styles.card, pressed && styles.pressed]}
        >
          <View style={styles.iconSq}>
            <AppIcon icon={feather('package')} size={20} color={AI_SETUP_TEAL} />
          </View>
          <View style={styles.copy}>
            <Text style={styles.name} numberOfLines={1}>
              {item.name}
            </Text>
            <Text style={styles.meta} numberOfLines={1}>
              {item.price || tr('productsImagesLabel')}
              {item.availability === 'out_of_stock' ? ` · ${tr('productsOutOfStockBadge')}` : ''}
            </Text>
          </View>
          <AppIcon icon={feather('chevron-right')} size={18} color={MUTED} />
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 12, paddingBottom: 28, flexGrow: 1 },
  import: {
    color: AI_SETUP_TEAL,
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    fontWeight: '700',
  },
  empty: { color: MUTED, fontFamily: fonts.body, fontSize: 14 },
  card: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: BORDER,
    borderRadius: 12,
    padding: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  iconSq: {
    width: 44,
    height: 44,
    borderRadius: 10,
    backgroundColor: SOFT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  copy: { flex: 1, gap: 4 },
  name: { color: INK, fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  meta: { color: MUTED, fontFamily: fonts.body, fontSize: 13 },
  pressed: { opacity: 0.7 },
});
