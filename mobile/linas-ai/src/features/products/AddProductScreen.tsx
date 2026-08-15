import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { pickImageAttachment } from '../chat/v2/pickAttachment';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { Field } from '../cm/editors/Field';
import { ScreenChrome } from '../shared/ScreenChrome';
import {
  MAX_PRODUCT_IMAGES,
  createProduct,
  fetchProduct,
  joinCommaList,
  parseCommaList,
  updateProduct,
  uploadProductImage,
  type ProductWriteInput,
} from './productsApi';

type ImageRow = { media_id: string; sort_order: number; previewUri?: string };

type Props = {
  productId?: string | null;
  onBack: () => void;
  onSaved: () => void;
};

export function AddProductScreen({ productId, onBack, onSaved }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const editing = Boolean(productId);
  const [loading, setLoading] = useState(editing);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [price, setPrice] = useState('');
  const [sizesText, setSizesText] = useState('');
  const [colorsText, setColorsText] = useState('');
  const [note, setNote] = useState('');
  const [images, setImages] = useState<ImageRow[]>([]);
  const [links, setLinks] = useState<{ url: string; label?: string }[]>([{ url: '', label: '' }]);

  useEffect(() => {
    if (!productId) return;
    void (async () => {
      setLoading(true);
      try {
        const product = await fetchProduct(productId);
        setName(product.name);
        setPrice(product.price ?? '');
        setSizesText(joinCommaList(product.sizes ?? []));
        setColorsText(joinCommaList(product.colors ?? []));
        setNote(product.note ?? '');
        setImages(
          (product.images ?? []).map((img) => ({
            media_id: img.media_id,
            sort_order: img.sort_order,
          })),
        );
        const productLinks = product.links ?? [];
        setLinks(
          productLinks.length
            ? productLinks.map((link) => ({ url: link.url, label: link.label ?? '' }))
            : [{ url: '', label: '' }],
        );
      } catch {
        setError(tr('productsLoadError'));
      } finally {
        setLoading(false);
      }
    })();
  }, [productId, tr]);

  const addImage = async () => {
    if (images.length >= MAX_PRODUCT_IMAGES) {
      setError(tr('productsMaxImages', { max: MAX_PRODUCT_IMAGES }));
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const picked = await pickImageAttachment();
      if (!picked) return;
      const uploaded = await uploadProductImage({
        uri: picked.uri,
        name: picked.name,
        mimeType: picked.mimeType,
      });
      setImages((rows) => [
        ...rows,
        { media_id: uploaded.media_id, sort_order: rows.length, previewUri: picked.uri },
      ]);
    } catch {
      setError(tr('productsUploadError'));
    } finally {
      setUploading(false);
    }
  };

  const removeImage = (mediaId: string) => {
    setImages((rows) =>
      rows
        .filter((row) => row.media_id !== mediaId)
        .map((row, index) => ({ ...row, sort_order: index })),
    );
  };

  const buildPayload = (): ProductWriteInput => ({
    name: name.trim(),
    price: price.trim() || null,
    sizes: parseCommaList(sizesText),
    colors: parseCommaList(colorsText),
    note: note.trim() || null,
    images: images.map((row, index) => ({ media_id: row.media_id, sort_order: index })),
    links: links
      .map((link, index) => ({
        url: link.url.trim(),
        label: (link.label || '').trim() || null,
        sort_order: index,
      }))
      .filter((link) => link.url),
  });

  const save = async () => {
    if (!name.trim()) {
      setError(tr('productsNameRequired'));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = buildPayload();
      if (editing && productId) {
        await updateProduct(productId, payload);
      } else {
        await createProduct(payload);
      }
      onSaved();
    } catch {
      setError(tr('productsSaveError'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <ScreenChrome
        title={tr(editing ? 'productsEditTitle' : 'productsAddTitle')}
        onBack={onBack}
      >
        <ActivityIndicator color={colors.accent} />
      </ScreenChrome>
    );
  }

  return (
    <ScreenChrome
      title={tr(editing ? 'productsEditTitle' : 'productsAddTitle')}
      onBack={onBack}
    >
      <ScrollView contentContainerStyle={styles.form} keyboardShouldPersistTaps="handled">
        {error ? <Text style={{ color: colors.danger }}>{error}</Text> : null}
        <Field label={tr('productsName')} value={name} onChange={setName} />
        <Field label={tr('productsPrice')} value={price} onChange={setPrice} />
        <Field
          label={tr('productsSizes')}
          value={sizesText}
          onChange={setSizesText}
          placeholder={tr('productsCommaHint')}
        />
        <Field
          label={tr('productsColors')}
          value={colorsText}
          onChange={setColorsText}
          placeholder={tr('productsCommaHint')}
        />
        <Field label={tr('productsNote')} value={note} onChange={setNote} multiline />

        <Text style={styles.section}>{tr('productsImagesSection')}</Text>
        <View style={styles.imageRow}>
          {images.map((img) => (
            <View key={img.media_id} style={styles.thumbWrap}>
              {img.previewUri ? (
                <Image source={{ uri: img.previewUri }} style={styles.thumb} />
              ) : (
                <View style={[styles.thumb, styles.thumbPlaceholder, { borderColor: colors.border }]}>
                  <Text style={{ fontSize: 10, color: colors.muted }}>{img.media_id.slice(-6)}</Text>
                </View>
              )}
              <Pressable onPress={() => removeImage(img.media_id)}>
                <Text style={{ color: colors.danger, fontSize: 12 }}>{tr('productsRemove')}</Text>
              </Pressable>
            </View>
          ))}
        </View>
        <PrimaryButton
          label={uploading ? tr('productsUploading') : tr('productsAddImage')}
          onPress={() => void addImage()}
          disabled={uploading || images.length >= MAX_PRODUCT_IMAGES}
        />

        <Text style={styles.section}>{tr('productsLinksSection')}</Text>
        {links.map((link, index) => (
          <View key={`link-${index}`} style={styles.linkBlock}>
            <Field
              label={tr('productsLinkUrl')}
              value={link.url}
              onChange={(value) =>
                setLinks((rows) =>
                  rows.map((row, i) => (i === index ? { ...row, url: value } : row)),
                )
              }
            />
            <Field
              label={tr('productsLinkLabel')}
              value={link.label ?? ''}
              onChange={(value) =>
                setLinks((rows) =>
                  rows.map((row, i) => (i === index ? { ...row, label: value } : row)),
                )
              }
            />
          </View>
        ))}
        <Pressable
          onPress={() => setLinks((rows) => [...rows, { url: '', label: '' }])}
          style={styles.addLink}
        >
          <Text style={{ color: colors.accent }}>{tr('productsAddLink')}</Text>
        </Pressable>

        <PrimaryButton
          label={saving ? tr('productsSaving') : tr('productsSave')}
          onPress={() => void save()}
          disabled={saving}
        />
      </ScrollView>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  form: { gap: spacing.md, paddingBottom: spacing.xl },
  section: { fontFamily: fonts.bodyMedium, fontSize: 15, color: '#10221A', marginTop: spacing.sm },
  imageRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  thumbWrap: { alignItems: 'center', gap: 4 },
  thumb: { width: 72, height: 72, borderRadius: radii.sm },
  thumbPlaceholder: {
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  linkBlock: { gap: spacing.xs },
  addLink: { paddingVertical: spacing.xs },
});
