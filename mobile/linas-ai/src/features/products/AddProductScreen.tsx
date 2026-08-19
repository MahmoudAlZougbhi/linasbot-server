import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text } from 'react-native';

import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import { LinasSparkleIcon } from '../../components/LinasSparkleIcon';
import { pickImageAttachment } from '../chat/v2/pickAttachment';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import { pickServiceFile, pickServiceVideo } from '../services/servicePick';
import { ProductDetailsStep } from './ProductDetailsStep';
import { ProductMediaLinksStep } from './ProductMediaLinksStep';
import { ProductStepper } from './ProductStepper';
import { PR_CANVAS, PR_DANGER, PR_TEAL } from './productChrome';
import {
  mergeProductLinks,
  splitProductLinks,
  type AssetRef,
  type ChannelLink,
  type ChannelPlatform,
  type ShareableLink,
} from './productModel';
import {
  MAX_PRODUCT_IMAGES,
  createProduct,
  fetchProduct,
  joinCommaList,
  parseCommaList,
  updateProduct,
  uploadProductMedia,
  type ProductWriteInput,
} from './productsApi';

type ImageRow = { media_id: string; sort_order: number; previewUri?: string };

type Props = {
  productId?: string | null;
  onBack: () => void;
  onSaved: () => void;
};

export function AddProductScreen({ productId, onBack, onSaved }: Props) {
  const { tr } = useI18n();
  const editing = Boolean(productId);
  const [step, setStep] = useState<1 | 2>(1);
  const [loading, setLoading] = useState(editing);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [price, setPrice] = useState('');
  const [sizesText, setSizesText] = useState('');
  const [colorsText, setColorsText] = useState('');
  const [note, setNote] = useState('');
  const [availability, setAvailability] = useState<'in_stock' | 'out_of_stock'>('in_stock');
  const [images, setImages] = useState<ImageRow[]>([]);
  const [shareable, setShareable] = useState<ShareableLink[]>([]);
  const [channel, setChannel] = useState<ChannelLink[]>([]);
  const [video, setVideo] = useState<AssetRef | null>(null);
  const [file, setFile] = useState<AssetRef | null>(null);

  useEffect(() => {
    if (!productId) return;
    void (async () => {
      setLoading(true);
      try {
        const product = await fetchProduct(productId);
        setName(product.name);
        setDescription(product.description ?? '');
        setPrice(String(product.price || '').replace(/^\$/, ''));
        setSizesText(joinCommaList(product.sizes ?? []));
        setColorsText(joinCommaList(product.colors ?? []));
        setNote(product.note ?? '');
        setAvailability(product.availability === 'out_of_stock' ? 'out_of_stock' : 'in_stock');
        setImages(
          (product.images ?? []).map((img) => ({
            media_id: img.media_id,
            sort_order: img.sort_order,
          })),
        );
        const parts = splitProductLinks(product.links);
        setShareable(parts.shareable);
        setChannel(parts.channel);
        setVideo(parts.video);
        setFile(parts.file);
      } catch {
        setError(tr('productsLoadError'));
      } finally {
        setLoading(false);
      }
    })();
  }, [productId, tr]);

  const upload = async (picked: { uri: string; name: string; mimeType: string } | null) => {
    if (!picked) return null;
    setUploading(true);
    setError(null);
    try {
      const uploaded = await uploadProductMedia({
        uri: picked.uri,
        name: picked.name,
        mimeType: picked.mimeType,
      });
      return { media_id: uploaded.media_id, previewUri: picked.uri, filename: picked.name };
    } catch {
      setError(tr('productsUploadError'));
      return null;
    } finally {
      setUploading(false);
    }
  };

  const addImage = async () => {
    if (images.length >= MAX_PRODUCT_IMAGES) {
      setError(tr('productsMaxImages'));
      return;
    }
    const uploaded = await upload(await pickImageAttachment());
    if (!uploaded) return;
    setImages((rows) => [
      ...rows,
      { media_id: uploaded.media_id, sort_order: rows.length, previewUri: uploaded.previewUri },
    ]);
  };

  const buildPayload = (): ProductWriteInput => ({
    name: name.trim(),
    description: description.trim(),
    price: price.trim() ? (price.trim().startsWith('$') ? price.trim() : `$${price.trim()}`) : null,
    sizes: parseCommaList(sizesText),
    colors: parseCommaList(colorsText),
    note: note.trim() || null,
    availability,
    images: images.map((row, index) => ({ media_id: row.media_id, sort_order: index })),
    links: mergeProductLinks({ shareable, channel, video, file }),
  });

  const save = async () => {
    if (!name.trim()) {
      setError(tr('productsNameRequired'));
      setStep(1);
      return;
    }
    if (!description.trim()) {
      setError(tr('productsDescriptionRequired'));
      setStep(1);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = buildPayload();
      if (editing && productId) await updateProduct(productId, payload);
      else await createProduct(payload);
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
        canvasColor={PR_CANVAS}
        headerLead={<LinasSparkleIcon size={22} color={PR_TEAL} />}
      >
        <LinasLoadingIndicator variant="screen" />
      </ScreenChrome>
    );
  }

  return (
    <ScreenChrome
      title={tr(editing ? 'productsEditTitle' : 'productsAddTitle')}
      onBack={step === 2 ? () => setStep(1) : onBack}
      canvasColor={PR_CANVAS}
      headerLead={<LinasSparkleIcon size={22} color={PR_TEAL} />}
    >
      <ScrollView contentContainerStyle={styles.form} keyboardShouldPersistTaps="handled">
        <ProductStepper
          step={step}
          detailsLabel={tr('productsStepDetails')}
          mediaLabel={tr('productsStepMedia')}
        />
        {error ? <Text style={styles.error}>{error}</Text> : null}
        {step === 1 ? (
          <ProductDetailsStep
            name={name}
            description={description}
            price={price}
            sizesText={sizesText}
            colorsText={colorsText}
            note={note}
            availability={availability}
            onChangeName={setName}
            onChangeDescription={setDescription}
            onChangePrice={setPrice}
            onChangeSizes={setSizesText}
            onChangeColors={setColorsText}
            onChangeNote={setNote}
            onChangeAvailability={setAvailability}
            onContinue={() => {
              if (!name.trim()) {
                setError(tr('productsNameRequired'));
                return;
              }
              if (!description.trim()) {
                setError(tr('productsDescriptionRequired'));
                return;
              }
              setError(null);
              setStep(2);
            }}
            tr={tr}
          />
        ) : (
          <ProductMediaLinksStep
            images={images}
            video={video}
            file={file}
            shareable={shareable}
            channel={channel}
            uploading={uploading}
            saving={saving}
            onAddImage={() => void addImage()}
            onRemoveImage={(mediaId) =>
              setImages((rows) =>
                rows
                  .filter((row) => row.media_id !== mediaId)
                  .map((row, index) => ({ ...row, sort_order: index })),
              )
            }
            onAddVideo={() =>
              void (async () => {
                const uploaded = await upload(await pickServiceVideo());
                if (uploaded) setVideo(uploaded);
              })()
            }
            onClearVideo={() => setVideo(null)}
            onAddFile={() =>
              void (async () => {
                const uploaded = await upload(await pickServiceFile());
                if (uploaded) setFile(uploaded);
              })()
            }
            onClearFile={() => setFile(null)}
            onAddShareable={(url) => setShareable((rows) => [...rows, { url }])}
            onRemoveShareable={(index) =>
              setShareable((rows) => rows.filter((_, i) => i !== index))
            }
            onAddChannel={(platform: ChannelPlatform, url) =>
              setChannel((rows) => [...rows, { platform, url }])
            }
            onRemoveChannel={(index) => setChannel((rows) => rows.filter((_, i) => i !== index))}
            onSave={() => void save()}
            tr={tr}
          />
        )}
      </ScrollView>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  form: { gap: 14, paddingBottom: 28 },
  error: { color: PR_DANGER, fontFamily: fonts.body, marginBottom: 4 },
});
