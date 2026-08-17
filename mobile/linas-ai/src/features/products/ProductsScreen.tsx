import { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import { LinasSparkleIcon } from '../../components/LinasSparkleIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import { ProductListView } from './ProductListView';
import { PR_CANVAS, PR_DANGER, PR_INK, PR_MUTED, PR_TEAL } from './productChrome';
import {
  fetchProducts,
  updateProductAvailability,
  type Product,
} from './productsApi';

type Props = {
  onBack?: () => void;
  onAdd: () => void;
  onImport: () => void;
  onOpenDetails: (productId: string) => void;
};

export function ProductsScreen({ onBack, onAdd, onImport, onOpenDetails }: Props) {
  const { tr } = useI18n();
  const [loading, setLoading] = useState(true);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [query, setQuery] = useState('');
  const [togglingId, setTogglingId] = useState<string | null>(null);

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

  const handleToggle = async (product: Product, next: 'in_stock' | 'out_of_stock') => {
    const prev = product.availability === 'out_of_stock' ? 'out_of_stock' : 'in_stock';
    if (prev === next) return;
    setTogglingId(product.id);
    setProducts((rows) =>
      rows.map((row) => (row.id === product.id ? { ...row, availability: next } : row)),
    );
    try {
      const updated = await updateProductAvailability(product, next);
      setProducts((rows) => rows.map((row) => (row.id === product.id ? updated : row)));
      setError(null);
    } catch {
      setProducts((rows) =>
        rows.map((row) => (row.id === product.id ? { ...row, availability: prev } : row)),
      );
      setError(tr('productsSaveError'));
    } finally {
      setTogglingId(null);
    }
  };

  return (
    <ScreenChrome
      title={tr('productsTitle')}
      hideTitle
      onBack={onBack}
      canvasColor={PR_CANVAS}
      headerLead={<LinasSparkleIcon size={22} color={PR_TEAL} />}
      headerRight={
        <Pressable
          onPress={onAdd}
          accessibilityRole="button"
          accessibilityLabel={tr('productsAdd')}
          style={({ pressed }) => [styles.addCircle, pressed && styles.pressed]}
        >
          <AppIcon icon={feather('plus')} size={22} color="#FFFFFF" />
        </Pressable>
      }
    >
      {loading && !hasLoadedOnce ? <LinasLoadingIndicator variant="screen" style={styles.loader} /> : null}
      {hasLoadedOnce && error ? <Text style={styles.error}>{error}</Text> : null}
      {hasLoadedOnce ? (
        <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
          <View style={styles.hero}>
            <Text style={styles.title}>{tr('productsTitle')}</Text>
            <Text style={styles.subtitle}>{tr('productsSubtitle')}</Text>
          </View>
          <ProductListView
            items={products}
            query={query}
            onQueryChange={setQuery}
            onAdd={onAdd}
            onImport={onImport}
            onSelect={onOpenDetails}
            onToggleStock={(product, next) => void handleToggle(product, next)}
            togglingId={togglingId}
            tr={tr}
          />
        </ScrollView>
      ) : null}
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  loader: { marginVertical: spacing.sm },
  list: { flexGrow: 1, paddingBottom: spacing.xl },
  hero: { gap: 6, marginBottom: 14 },
  title: {
    color: PR_INK,
    fontFamily: fonts.bodyMedium,
    fontSize: 28,
    fontWeight: '800',
    letterSpacing: -0.3,
  },
  subtitle: { color: PR_MUTED, fontFamily: fonts.body, fontSize: 14, lineHeight: 20 },
  error: { color: PR_DANGER, fontFamily: fonts.body, marginBottom: 8 },
  addCircle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: PR_TEAL,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pressed: { opacity: 0.7 },
});
