import { useEffect, useRef, useState } from 'react';
import {
  Dimensions,
  NativeScrollEvent,
  NativeSyntheticEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts } from '../../theme';
import { confirmAiSetupDelete } from '../cm/confirmAiSetupDelete';
import { ScreenChrome } from '../shared/ScreenChrome';
import { ProductAuthImage } from './ProductAuthImage';
import {
  PR_BORDER,
  PR_CANVAS,
  PR_DANGER,
  PR_INK,
  PR_MUTED,
  PR_RADIUS,
  PR_RADIUS_SM,
  PR_TEAL,
  PR_TEAL_SOFT,
} from './productChrome';
import { formatProductPrice, mediaSummary, splitProductLinks } from './productModel';
import { deleteProduct, fetchProduct, joinCommaList, type Product } from './productsApi';

type Props = {
  productId: string;
  onBack: () => void;
  onEdit: () => void;
  onDeleted: () => void;
};

const WIDTH = Dimensions.get('window').width - 32;

export function ProductDetailsScreen({ productId, onBack, onEdit, onDeleted }: Props) {
  const { tr } = useI18n();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [product, setProduct] = useState<Product | null>(null);
  const [index, setIndex] = useState(0);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        setProduct(await fetchProduct(productId));
        setError(null);
      } catch {
        setError(tr('productsLoadError'));
      } finally {
        setLoading(false);
      }
    })();
  }, [productId, tr]);

  const handleDelete = () => {
    confirmAiSetupDelete({
      title: tr('productsDeleteTitle'),
      body: tr('productsDeleteBody'),
      confirmLabel: tr('productsDeleteProduct'),
      cancelLabel: tr('usersCancel'),
      onConfirm: () => {
        void (async () => {
          try {
            await deleteProduct(productId);
            onDeleted();
          } catch {
            setError(tr('productsDeleteError'));
          }
        })();
      },
    });
  };

  const onScrollEnd = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const x = e.nativeEvent.contentOffset.x;
    setIndex(Math.round(x / WIDTH));
  };

  if (loading || !product) {
    return (
      <ScreenChrome title={tr('productsDetailsTitle')} onBack={onBack} canvasColor={PR_CANVAS}>
        {loading ? <LinasLoadingIndicator variant="screen" /> : null}
        {error ? <Text style={styles.error}>{error}</Text> : null}
      </ScreenChrome>
    );
  }

  const images = product.images ?? [];
  const inStock = product.availability !== 'out_of_stock';
  const parts = splitProductLinks(product.links);
  const sizes = joinCommaList(product.sizes ?? []);
  const colors = joinCommaList(product.colors ?? []);

  return (
    <ScreenChrome
      title={tr('productsDetailsTitle')}
      centerTitle
      onBack={onBack}
      canvasColor={PR_CANVAS}
      headerRight={
        <Pressable
          onPress={onEdit}
          accessibilityRole="button"
          style={({ pressed }) => [styles.editBtn, pressed && styles.pressed]}
        >
          <Text style={styles.editText}>{tr('productsEdit')}</Text>
        </Pressable>
      }
    >
      <ScrollView contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
        {error ? <Text style={styles.error}>{error}</Text> : null}

        {images.length ? (
          <View style={styles.carouselWrap}>
            <ScrollView
              ref={scrollRef}
              horizontal
              pagingEnabled
              showsHorizontalScrollIndicator={false}
              onMomentumScrollEnd={onScrollEnd}
              style={{ width: WIDTH }}
            >
              {images.map((img) => (
                <ProductAuthImage
                  key={img.media_id}
                  mediaId={img.media_id}
                  style={{ width: WIDTH, height: 220, borderRadius: PR_RADIUS }}
                />
              ))}
            </ScrollView>
            <View style={styles.badge}>
              <Text style={styles.badgeText}>
                {index + 1} / {images.length}
              </Text>
            </View>
            <View style={styles.dots}>
              {images.map((img, i) => (
                <View key={img.media_id} style={[styles.dot, i === index && styles.dotOn]} />
              ))}
            </View>
          </View>
        ) : (
          <View style={[styles.carouselWrap, styles.noImage]}>
            <AppIcon icon={feather('package')} size={36} color={PR_TEAL} />
          </View>
        )}

        <Text style={styles.name}>{product.name}</Text>
        <View style={styles.priceRow}>
          {product.price ? <Text style={styles.price}>{formatProductPrice(product.price)}</Text> : null}
          <View style={[styles.stockBadge, !inStock && styles.stockOut]}>
            <Text style={[styles.stockText, !inStock && styles.stockOutText]}>
              {inStock ? tr('productsAvailability_in_stock') : tr('productsOutOfStockBadge')}
            </Text>
          </View>
        </View>

        <View style={styles.group}>
          <Row label={tr('productsSizes')} value={sizes || '—'} />
          <Row label={tr('productsColors')} value={colors || '—'} last />
        </View>

        {product.note ? (
          <View style={styles.noteBlock}>
            <Text style={styles.noteLabel}>{tr('productsNote')}</Text>
            <Text style={styles.noteBody}>{product.note}</Text>
          </View>
        ) : null}

        <View style={styles.group}>
          <NavRow
            icon={feather('image')}
            title={tr('productsMediaFilesRow')}
            subtitle={mediaSummary(product)}
          />
          <NavRow
            icon={feather('link')}
            title={tr('productsShareLinksSection')}
            subtitle={
              parts.shareable.length === 1
                ? tr('productsLinksCountOne')
                : tr('productsLinksCount').replace('{count}', String(parts.shareable.length))
            }
          />
          <NavRow
            icon={feather('play-circle')}
            title={tr('productsChannelVideosRow')}
            subtitle={
              parts.channel.length === 1
                ? tr('productsChannelCountOne')
                : tr('productsChannelCount').replace('{count}', String(parts.channel.length))
            }
            last
          />
        </View>

        <View style={styles.info}>
          <View style={styles.infoIcon}>
            <Text style={styles.infoI}>i</Text>
          </View>
          <Text style={styles.infoText}>{tr('productsDetailsInfo')}</Text>
        </View>

        <Pressable
          onPress={handleDelete}
          accessibilityRole="button"
          style={({ pressed }) => [styles.deleteBtn, pressed && styles.pressed]}
        >
          <Text style={styles.deleteText}>{tr('productsDeleteProduct')}</Text>
        </Pressable>
      </ScrollView>
    </ScreenChrome>
  );
}

function Row({ label, value, last }: { label: string; value: string; last?: boolean }) {
  return (
    <View style={[styles.row, last && styles.rowLast]}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue} numberOfLines={1}>
        {value}
      </Text>
      <AppIcon icon={feather('chevron-right')} size={16} color={PR_MUTED} />
    </View>
  );
}

function NavRow({
  icon,
  title,
  subtitle,
  last,
}: {
  icon: ReturnType<typeof feather>;
  title: string;
  subtitle: string;
  last?: boolean;
}) {
  return (
    <View style={[styles.navRow, last && styles.rowLast]}>
      <View style={styles.navIcon}>
        <AppIcon icon={icon} size={16} color={PR_TEAL} />
      </View>
      <View style={styles.navCopy}>
        <Text style={styles.navTitle}>{title}</Text>
        <Text style={styles.navSub}>{subtitle}</Text>
      </View>
      <AppIcon icon={feather('chevron-right')} size={16} color={PR_MUTED} />
    </View>
  );
}

const styles = StyleSheet.create({
  body: { gap: 14, paddingBottom: 36 },
  error: { color: PR_DANGER, fontFamily: fonts.body },
  editBtn: {
    borderWidth: 1.5,
    borderColor: PR_TEAL,
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 7,
  },
  editText: { color: PR_TEAL, fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '700' },
  carouselWrap: { borderRadius: PR_RADIUS, overflow: 'hidden', backgroundColor: '#FFFFFF' },
  noImage: {
    height: 180,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: PR_TEAL_SOFT,
  },
  badge: {
    position: 'absolute',
    top: 12,
    left: 12,
    backgroundColor: 'rgba(0,0,0,0.45)',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  badgeText: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 12 },
  dots: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 10,
  },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#CBD5E1' },
  dotOn: { backgroundColor: PR_TEAL },
  name: { color: PR_INK, fontFamily: fonts.bodyMedium, fontSize: 24, fontWeight: '800' },
  priceRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  price: { color: PR_INK, fontFamily: fonts.bodyMedium, fontSize: 18, fontWeight: '700' },
  stockBadge: {
    backgroundColor: PR_TEAL_SOFT,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  stockOut: { backgroundColor: '#F1F5F9' },
  stockText: { color: PR_TEAL, fontFamily: fonts.bodyMedium, fontSize: 12, fontWeight: '700' },
  stockOutText: { color: PR_MUTED },
  group: {
    backgroundColor: '#FFFFFF',
    borderRadius: PR_RADIUS,
    borderWidth: 1,
    borderColor: PR_BORDER,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 14,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: PR_BORDER,
  },
  rowLast: { borderBottomWidth: 0 },
  rowLabel: { color: PR_INK, fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '600', width: 64 },
  rowValue: { flex: 1, color: PR_MUTED, fontFamily: fonts.body, fontSize: 14 },
  noteBlock: { gap: 6 },
  noteLabel: { color: PR_INK, fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
  noteBody: { color: PR_MUTED, fontFamily: fonts.body, fontSize: 14, lineHeight: 20 },
  navRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: PR_BORDER,
  },
  navIcon: {
    width: 36,
    height: 36,
    borderRadius: 10,
    backgroundColor: PR_TEAL_SOFT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  navCopy: { flex: 1, gap: 2 },
  navTitle: { color: PR_INK, fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
  navSub: { color: PR_MUTED, fontFamily: fonts.body, fontSize: 12 },
  info: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    backgroundColor: PR_TEAL_SOFT,
    borderRadius: PR_RADIUS_SM,
    padding: 12,
  },
  infoIcon: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 1.5,
    borderColor: PR_TEAL,
    alignItems: 'center',
    justifyContent: 'center',
  },
  infoI: { color: PR_TEAL, fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '800' },
  infoText: { flex: 1, color: PR_TEAL, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  deleteBtn: {
    borderWidth: 1,
    borderColor: PR_BORDER,
    borderRadius: PR_RADIUS_SM,
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FFFFFF',
  },
  deleteText: { color: PR_DANGER, fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
  pressed: { opacity: 0.75 },
});
