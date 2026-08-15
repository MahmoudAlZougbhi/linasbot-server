import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import { deleteProduct, fetchProducts, type Product } from './productsApi';

type Props = {
  onBack?: () => void;
  onAdd: () => void;
  onEdit: (productId: string) => void;
};

export function ProductsScreen({ onBack, onAdd, onEdit }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const [loading, setLoading] = useState(true);
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
      {loading ? <ActivityIndicator color={colors.accent} style={styles.loader} /> : null}
      {error ? <Text style={{ color: colors.danger }}>{error}</Text> : null}
      <PrimaryButton label={tr('productsAdd')} onPress={onAdd} />
      <FlatList
        data={products}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          !loading ? (
            <Text style={[styles.empty, { color: colors.muted }]}>{tr('productsEmpty')}</Text>
          ) : null
        }
        renderItem={({ item }) => (
          <View style={[styles.card, { borderColor: colors.border }]}>
            <Pressable onPress={() => onEdit(item.id)} style={styles.cardMain}>
              <Text style={styles.name}>{item.name}</Text>
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
});
