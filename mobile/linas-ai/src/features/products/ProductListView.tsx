import { Pressable, StyleSheet, Switch, Text, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import type { StringKey } from '../../i18n';
import { fonts } from '../../theme';
import { ProductAuthImage } from './ProductAuthImage';
import {
  PR_BORDER,
  PR_INK,
  PR_MUTED,
  PR_RADIUS,
  PR_RADIUS_SM,
  PR_TEAL,
} from './productChrome';
import { formatProductPrice, variantMetaLabel } from './productModel';
import type { Product } from './productsApi';

type Props = {
  items: Product[];
  query: string;
  onQueryChange: (value: string) => void;
  onAdd: () => void;
  onImport: () => void;
  onSelect: (id: string) => void;
  onToggleStock: (product: Product, next: 'in_stock' | 'out_of_stock') => void;
  togglingId?: string | null;
  tr: (key: StringKey) => string;
};

export function ProductListView({
  items,
  query,
  onQueryChange,
  onAdd,
  onImport,
  onSelect,
  onToggleStock,
  togglingId,
  tr,
}: Props) {
  const q = query.trim().toLowerCase();
  const visible = q ? items.filter((item) => item.name.toLowerCase().includes(q)) : items;

  return (
    <View style={styles.wrap}>
      <Pressable
        onPress={onAdd}
        accessibilityRole="button"
        accessibilityLabel={tr('productsAdd')}
        style={({ pressed }) => [styles.addBtn, pressed && styles.pressed]}
      >
        <Text style={styles.addBtnText}>{tr('productsAdd')}</Text>
      </Pressable>

      <View style={styles.search}>
        <AppIcon icon={feather('search')} size={18} color={PR_MUTED} />
        <TextInput
          value={query}
          onChangeText={onQueryChange}
          placeholder={tr('productsSearch')}
          placeholderTextColor={PR_MUTED}
          style={styles.searchInput}
          autoCapitalize="none"
          autoCorrect={false}
          accessibilityLabel={tr('productsSearch')}
        />
      </View>

      <Pressable onPress={onImport} accessibilityRole="button" accessibilityLabel={tr('productsImport')}>
        <Text style={styles.import}>{tr('productsImport')}</Text>
      </Pressable>

      {visible.length === 0 ? <Text style={styles.empty}>{tr('productsEmpty')}</Text> : null}

      {visible.map((item) => {
        const inStock = item.availability !== 'out_of_stock';
        const thumb = item.images?.[0]?.media_id;
        return (
          <Pressable
            key={item.id}
            onPress={() => onSelect(item.id)}
            accessibilityRole="button"
            accessibilityLabel={item.name}
            style={({ pressed }) => [styles.card, pressed && styles.pressed]}
          >
            <ProductAuthImage
              mediaId={thumb}
              style={styles.thumb}
              placeholderIcon={<AppIcon icon={feather('package')} size={20} color={PR_TEAL} />}
            />
            <View style={styles.copy}>
              <Text style={styles.name} numberOfLines={1}>
                {item.name}
              </Text>
              {item.price ? (
                <Text style={styles.price} numberOfLines={1}>
                  {formatProductPrice(item.price)}
                </Text>
              ) : null}
              <View style={styles.stockRow} onStartShouldSetResponder={() => true}>
                <Text style={[styles.stockLabel, !inStock && styles.stockOut]}>
                  {inStock ? tr('productsAvailability_in_stock') : tr('productsOutOfStockBadge')}
                </Text>
                <Switch
                  value={inStock}
                  disabled={togglingId === item.id}
                  onValueChange={(on) =>
                    onToggleStock(item, on ? 'in_stock' : 'out_of_stock')
                  }
                  trackColor={{ false: '#CBD5E1', true: PR_TEAL }}
                  thumbColor="#FFFFFF"
                  ios_backgroundColor="#CBD5E1"
                  accessibilityLabel={tr('productsAvailabilitySection')}
                />
              </View>
              <Text style={styles.meta} numberOfLines={1}>
                {variantMetaLabel(item)}
              </Text>
            </View>
            <AppIcon icon={feather('chevron-right')} size={18} color={PR_MUTED} />
          </Pressable>
        );
      })}

      <Text style={styles.footer}>{tr('productsStockFooter')}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 12, paddingBottom: 28, flexGrow: 1 },
  addBtn: {
    backgroundColor: PR_TEAL,
    borderRadius: 999,
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  addBtnText: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  search: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: PR_BORDER,
    borderRadius: PR_RADIUS_SM,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  searchInput: {
    flex: 1,
    color: PR_INK,
    fontFamily: fonts.body,
    fontSize: 15,
    padding: 0,
  },
  import: {
    color: PR_TEAL,
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    fontWeight: '700',
  },
  empty: { color: PR_MUTED, fontFamily: fonts.body, fontSize: 14 },
  card: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: PR_BORDER,
    borderRadius: PR_RADIUS,
    padding: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  thumb: { width: 56, height: 56, borderRadius: 12 },
  copy: { flex: 1, gap: 2 },
  name: { color: PR_INK, fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  price: { color: PR_INK, fontFamily: fonts.body, fontSize: 14 },
  stockRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 2 },
  stockLabel: { color: PR_TEAL, fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '600' },
  stockOut: { color: PR_MUTED },
  meta: { color: PR_MUTED, fontFamily: fonts.body, fontSize: 12, marginTop: 2 },
  footer: {
    color: PR_MUTED,
    fontFamily: fonts.body,
    fontSize: 13,
    textAlign: 'center',
    marginTop: 'auto',
    paddingTop: 16,
    lineHeight: 18,
  },
  pressed: { opacity: 0.7 },
});
