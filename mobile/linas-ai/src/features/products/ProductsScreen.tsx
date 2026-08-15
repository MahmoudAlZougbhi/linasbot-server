import { useCallback, useEffect, useState } from 'react';
import {
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import { deleteProduct, fetchProducts, type Product } from './productsApi';

type Props = {
  onBack?: () => void;
  onAdd: () => void;
  onImport: () => void;
  onEdit: (productId: string) => void;
};

export function ProductsScreen({ onBack, onAdd, onImport, onEdit }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const [loading, setLoading] = useState(true);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [products, setProducts] = useState<Product[]>([]);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchProducts();
      setProducts(res.products);
      setError(null);
    } catch {
      setError(tr('productsLoadError'));
    } finally {
      setLoading(false);
      setHasLoadedOnce(true);
    }
  }, [tr]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const handleDelete = async (productId: string) => {
    try {
      await deleteProduct(productId);
      setProducts((rows) => rows.filter((row) => row.id !== productId));
    } catch {
      setError(tr('productsDeleteError'));
    }
  };

  return (
    <ScreenChrome title={tr('productsTitle')} subtitle={tr('productsSubtitle')} onBack={onBack}>
      {loading && !hasLoadedOnce ? <LinasLoadingIndicator variant="screen" style={styles.loader} /> : null}
      {hasLoadedOnce && error ? <Text style={{ color: colors.danger }}>{error}</Text> : null}
      {hasLoadedOnce ? (
        <>
      <PrimaryButton label={tr('productsAdd')} onPress={onAdd} />
      <PrimaryButton label={tr('productsImport')} onPress={onImport} />
      <FlatList
        data={products}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <Text style={[styles.empty, { color: colors.muted }]}>{tr('productsEmpty')}</Text>
        }
        renderItem={({ item }) => (
          <View style={[styles.card, { borderColor: colors.border }]}>
            <Pressable onPress={() => onEdit(item.id)} style={styles.cardMain}>
              <Text style={styles.name}>{item.name}</Text>
              {item.availability === 'out_of_stock' ? (
                <Text style={styles.badge}>{tr('productsOutOfStockBadge')}</Text>
              ) : null}
              {item.price ? <Text style={{ color: colors.muted }}>{item.price}</Text> : null}
              <Text style={{ color: colors.muted, fontSize: 12 }}>
                {item.images?.length ?? 0} {tr('productsImagesLabel')}
              </Text>
            </Pressable>
            <Pressable onPress={() => void handleDelete(item.id)} accessibilityRole="button">
              <Text style={{ color: colors.danger }}>{tr('productsDelete')}</Text>
            </Pressable>
          </View>
        )}
      />
        </>
      ) : null}
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  loader: { marginVertical: spacing.sm },
  list: { gap: spacing.sm, paddingTop: spacing.md, paddingBottom: spacing.xl },
  empty: { textAlign: 'center', marginTop: spacing.lg, fontFamily: fonts.body },
  card: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  cardMain: { flex: 1, gap: 4 },
  name: { fontFamily: fonts.bodyMedium, fontSize: 16, color: '#10221A' },
  badge: {
    fontFamily: fonts.bodyMedium,
    fontSize: 11,
    color: '#B45309',
    backgroundColor: '#FEF3C7',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    alignSelf: 'flex-start',
  },
});
