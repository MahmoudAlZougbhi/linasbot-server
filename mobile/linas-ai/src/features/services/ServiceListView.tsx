import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { PrimaryButton } from '../../components/PrimaryButton';
import type { StringKey } from '../../i18n';
import { fonts } from '../../theme';
import { SV_BORDER, SV_ICON_SQ, SV_MUTED, SV_RADIUS, SV_TEAL, SV_TEAL_DARK, SV_TEAL_SOFT } from './serviceChrome';
import { formatMoney, lowestAmount, type ServiceItem } from './serviceModel';

type Props = {
  items: ServiceItem[];
  query: string;
  onQueryChange: (value: string) => void;
  onAdd: () => void;
  onSelect: (id: string) => void;
  tr: (key: StringKey) => string;
};

export function ServiceListView({ items, query, onQueryChange, onAdd, onSelect, tr }: Props) {
  return (
    <View style={styles.wrap}>
      <View style={styles.heroRow}>
        <View style={styles.titleRow}>
          <Text style={styles.hero}>{tr('servicesTitle')}</Text>
          <Pressable
            onPress={onAdd}
            accessibilityRole="button"
            accessibilityLabel={tr('servicesAdd')}
            style={({ pressed }) => [styles.plusCircle, pressed && styles.pressed]}
          >
            <Text style={styles.plusText}>+</Text>
          </Pressable>
        </View>
        <Text style={styles.subtitle}>{tr('servicesSubtitle')}</Text>
      </View>

      <PrimaryButton
        label={tr('servicesAdd')}
        onPress={onAdd}
        style={styles.addBtn}
      />

      <View style={styles.search}>
        <AppIcon icon={feather('search')} size={18} color={SV_MUTED} />
        <TextInput
          value={query}
          onChangeText={onQueryChange}
          placeholder={tr('servicesSearch')}
          placeholderTextColor={SV_MUTED}
          style={styles.searchInput}
          autoCapitalize="none"
          autoCorrect={false}
          accessibilityLabel={tr('servicesSearch')}
        />
      </View>

      {items.length === 0 ? <Text style={styles.empty}>{tr('servicesEmpty')}</Text> : null}
      {items.map((item) => (
        <ServiceCard key={item.id} item={item} onPress={() => onSelect(item.id)} tr={tr} />
      ))}

      <Text style={styles.footer}>{tr('servicesFooter')}</Text>
    </View>
  );
}

function priceFooterLabel(item: ServiceItem, tr: (key: StringKey) => string): string {
  const count = item.prices.length;
  if (count === 0) return tr('servicesFooterNone');
  const low = lowestAmount(item.prices);
  if (low != null && low <= 0) {
    return count === 1
      ? tr('servicesFooterOneFree')
      : tr('servicesFooterManyFree').replace('{count}', String(count));
  }
  const price = formatMoney(low ?? 0, item.prices[0]?.currency || 'USD');
  return count === 1
    ? tr('servicesFooterOneFrom').replace('{price}', price)
    : tr('servicesFooterManyFrom').replace('{count}', String(count)).replace('{price}', price);
}

function ServiceCard({
  item,
  onPress,
  tr,
}: {
  item: ServiceItem;
  onPress: () => void;
  tr: (key: StringKey) => string;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={item.name}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}
    >
      <View style={styles.cardTop}>
        <View style={styles.iconSq}>
          <AppIcon icon={feather('tag')} size={18} color={SV_TEAL} />
        </View>
        <View style={styles.copy}>
          <Text style={styles.name} numberOfLines={1}>
            {item.name}
          </Text>
          {item.note ? (
            <Text style={styles.note} numberOfLines={2}>
              {item.note}
            </Text>
          ) : null}
        </View>
        <AppIcon icon={feather('chevron-right')} size={18} color={SV_MUTED} />
      </View>
      <View style={styles.divider} />
      <View style={styles.cardFoot}>
        <View style={styles.priceMeta}>
          <AppIcon icon={feather('tag')} size={12} color={SV_TEAL} />
          <Text style={styles.footText}>{priceFooterLabel(item, tr)}</Text>
        </View>
        <Text style={styles.mediaText}>
          {tr('servicesMediaCount').replace('{count}', String(item.attachments.length))}
        </Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 12, paddingBottom: 28, flexGrow: 1 },
  heroRow: { marginTop: 4, gap: 6 },
  titleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  hero: {
    color: SV_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 28,
    fontWeight: '700',
  },
  plusCircle: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: SV_TEAL,
    alignItems: 'center',
    justifyContent: 'center',
  },
  plusText: { color: '#FFFFFF', fontSize: 22, fontWeight: '600', marginTop: -1 },
  subtitle: { color: SV_MUTED, fontFamily: fonts.body, fontSize: 15 },
  addBtn: { backgroundColor: SV_TEAL, borderRadius: SV_RADIUS },
  search: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: SV_BORDER,
    borderRadius: SV_RADIUS,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  searchInput: {
    flex: 1,
    color: SV_TEAL_DARK,
    fontFamily: fonts.body,
    fontSize: 15,
    padding: 0,
  },
  empty: { color: SV_MUTED, fontFamily: fonts.body, fontSize: 14 },
  card: {
    backgroundColor: '#FFFFFF',
    borderColor: SV_BORDER,
    borderWidth: 1,
    borderRadius: SV_RADIUS,
    padding: 14,
    gap: 10,
  },
  cardTop: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  iconSq: {
    width: SV_ICON_SQ,
    height: SV_ICON_SQ,
    borderRadius: 10,
    backgroundColor: SV_TEAL_SOFT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  copy: { flex: 1, gap: 4 },
  name: {
    color: SV_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
    fontWeight: '700',
  },
  note: { color: SV_MUTED, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  divider: { height: StyleSheet.hairlineWidth, backgroundColor: SV_BORDER },
  cardFoot: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  priceMeta: { flexDirection: 'row', alignItems: 'center', gap: 6, flex: 1 },
  footText: { color: SV_MUTED, fontFamily: fonts.body, fontSize: 12, flex: 1 },
  mediaText: { color: SV_MUTED, fontFamily: fonts.body, fontSize: 12 },
  footer: {
    color: SV_MUTED,
    fontFamily: fonts.body,
    fontSize: 13,
    textAlign: 'center',
    marginTop: 'auto',
    paddingTop: 16,
    lineHeight: 18,
  },
  pressed: { opacity: 0.7 },
});
