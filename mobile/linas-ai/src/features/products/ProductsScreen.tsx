import { useCallback, useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text } from 'react-native';

import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import { ProductListView } from './ProductListView';
import { fetchProducts, type Product } from './productsApi';

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
  const [query, setQuery] = useState('');

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

  return (
    <ScreenChrome title={tr('productsTitle')} subtitle={tr('productsSubtitle')} compactTitle onBack={onBack}>
      {loading && !hasLoadedOnce ? <LinasLoadingIndicator variant="screen" style={styles.loader} /> : null}
      {hasLoadedOnce && error ? <Text style={[styles.error, { color: colors.danger }]}>{error}</Text> : null}
      {hasLoadedOnce ? (
        <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
          <ProductListView
            items={products}
            query={query}
            onQueryChange={setQuery}
            onAdd={onAdd}
            onImport={onImport}
            onSelect={onEdit}
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
  error: { fontFamily: fonts.body, marginBottom: 8 },
});
