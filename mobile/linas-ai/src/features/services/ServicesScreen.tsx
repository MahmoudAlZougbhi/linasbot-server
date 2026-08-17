import { useMemo, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import { LinasSparkleIcon } from '../../components/LinasSparkleIcon';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import { asRecordList, newId } from '../cm/cmApi';
import type { CmProposalReview } from '../cm/cmProposalReview';
import { useCmDraft } from '../cm/useCmDraft';
import { ServiceEditView } from './ServiceEditView';
import { ServiceListView } from './ServiceListView';
import { ServicePriceView } from './ServicePriceView';
import { SV_CANVAS, SV_TEAL } from './serviceChrome';
import { ResourceMetaModal } from '../cm/resources/ResourceMetaModal';
import {
  buildPriceEntry,
  createCatalogItem,
  emptyPriceDraft,
  ensureDimensionDefs,
  matchesServiceQuery,
  parseAmount,
  parseServices,
  patchCatalogItem,
  priceDraftFromEntry,
  type PriceDraft,
  type ServiceItem,
} from './serviceModel';
import { useServiceMedia } from './useServiceMedia';

type Props = {
  proposalReview?: CmProposalReview | null;
  onBack?: () => void;
};

type Mode = 'list' | 'edit' | 'price';

export function ServicesScreen({ proposalReview, onBack }: Props) {
  const { tr } = useI18n();
  const insets = useSafeAreaInsets();
  const pricesReview =
    proposalReview && (proposalReview.section === 'prices' || proposalReview.section === 'services')
      ? { ...proposalReview, section: 'prices' as const }
      : proposalReview;
  const draft = useCmDraft('prices', pricesReview);
  const [mode, setMode] = useState<Mode>('list');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [priceDraft, setPriceDraft] = useState<PriceDraft>(emptyPriceDraft());
  const [priceError, setPriceError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const items = useMemo(() => parseServices(draft.payload), [draft.payload]);
  const selected = items.find((item) => item.id === selectedId) || null;
  const visible = useMemo(
    () => items.filter((item) => matchesServiceQuery(item, query)),
    [items, query],
  );

  function setCatalogAndEntries(
    catalog: Record<string, unknown>[],
    entries: Record<string, unknown>[],
    dimensions?: Record<string, unknown>[],
  ) {
    draft.setPayload({
      ...draft.payload,
      catalog,
      price_entries: entries,
      ...(dimensions ? { dimension_definitions: dimensions } : {}),
    });
  }

  function catalogRows(): Record<string, unknown>[] {
    return asRecordList(draft.payload.catalog);
  }

  function entryRows(): Record<string, unknown>[] {
    return asRecordList(draft.payload.price_entries);
  }

  function patchSelected(patch: Partial<Pick<ServiceItem, 'name' | 'note' | 'attachments'>>) {
    if (!selected) return;
    setCatalogAndEntries(
      catalogRows().map((row) =>
        String(row.id) === selected.id
          ? patchCatalogItem(row, {
              name: patch.name ?? selected.name,
              note: patch.note ?? selected.note,
              attachments: patch.attachments ?? selected.attachments,
            })
          : row,
      ),
      entryRows(),
    );
  }

  const media = useServiceMedia(selected, patchSelected, tr);

  function handleAdd() {
    const id = newId('svc');
    setCatalogAndEntries([createCatalogItem(id), ...catalogRows()], entryRows());
    setSelectedId(id);
    setMode('edit');
    media.setUploadError(null);
    setSaveError(null);
  }

  function goList() {
    if (
      selected &&
      !selected.name.trim() &&
      !selected.note.trim() &&
      !selected.prices.length &&
      !selected.attachments.length
    ) {
      setCatalogAndEntries(
        catalogRows().filter((row) => String(row.id) !== selected.id),
        entryRows(),
      );
    }
    setMode('list');
    setSelectedId(null);
    media.setUploadError(null);
    setSaveError(null);
  }

  function goEdit() {
    setMode('edit');
    setPriceDraft(emptyPriceDraft());
    setPriceError(null);
  }

  async function handleSaveService() {
    if (!selected?.name.trim()) {
      setSaveError(tr('servicesNameRequired'));
      return;
    }
    if (!draft.dirty) {
      goList();
      return;
    }
    const ok = await draft.save();
    if (ok) goList();
  }

  function upsertPrice(andAddAnother: boolean) {
    if (!selected) return;
    const amount = parseAmount(priceDraft.amountText);
    if (amount == null) {
      setPriceError(tr('servicesPriceRequired'));
      return;
    }
    const id = priceDraft.id || newId('entry');
    const nextEntry = buildPriceEntry(id, selected.id, priceDraft, amount);
    const existing = entryRows();
    const nextEntries = priceDraft.id
      ? existing.map((row) => (String(row.id) === id ? nextEntry : row))
      : [...existing, nextEntry];
    const dims = ensureDimensionDefs(asRecordList(draft.payload.dimension_definitions), priceDraft.details);
    setCatalogAndEntries(catalogRows(), nextEntries, dims);
    if (andAddAnother) {
      setPriceDraft(emptyPriceDraft());
      setPriceError(null);
      return;
    }
    goEdit();
  }

  function deletePrice() {
    if (!priceDraft.id) return;
    setCatalogAndEntries(
      catalogRows(),
      entryRows().filter((row) => String(row.id) !== priceDraft.id),
    );
    goEdit();
  }

  const chromeTitle =
    mode === 'list'
      ? tr('servicesTitle')
      : mode === 'price'
        ? tr(priceDraft.id ? 'servicesEditPriceTitle' : 'servicesAddPriceTitle')
        : tr('servicesEditTitle');

  return (
    <ScreenChrome
      title={chromeTitle}
      subtitle={
        mode === 'list'
          ? tr('servicesSubtitle')
          : mode === 'price'
            ? tr('servicesAddPriceSubtitle')
            : undefined
      }
      onBack={mode === 'list' ? onBack : mode === 'price' ? goEdit : goList}
      headerRight={mode === 'list' ? undefined : <LinasSparkleIcon size={18} color={SV_TEAL} />}
      canvasColor={SV_CANVAS}
    >
      {draft.loading ? <LinasLoadingIndicator variant="screen" /> : null}
      {draft.error ? <Text style={styles.error}>{draft.error}</Text> : null}
      {draft.conflict ? <Text style={styles.warn}>{draft.conflict}</Text> : null}
      {draft.proposalActive ? <Text style={styles.warn}>{tr('servicesProposalPreview')}</Text> : null}

      {!draft.loading && mode === 'list' ? (
        <ScrollView contentContainerStyle={styles.listScroll} showsVerticalScrollIndicator={false}>
          <ServiceListView
            items={visible}
            query={query}
            onQueryChange={setQuery}
            onAdd={handleAdd}
            onSelect={(id) => {
              setSelectedId(id);
              setMode('edit');
            }}
            tr={tr}
          />
        </ScrollView>
      ) : null}

      {!draft.loading && mode === 'edit' && selected ? (
        <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <ScrollView contentContainerStyle={styles.editScroll} showsVerticalScrollIndicator={false}>
            {saveError ? <Text style={styles.error}>{saveError}</Text> : null}
            <ServiceEditView
              item={selected}
              uploading={media.uploading}
              uploadError={media.uploadError}
              onName={(name) => patchSelected({ name })}
              onNote={(note) => patchSelected({ note })}
              onAddPrice={() => {
                setPriceDraft(emptyPriceDraft());
                setPriceError(null);
                setMode('price');
              }}
              onEditPrice={(id) => {
                const price = selected.prices.find((row) => row.id === id);
                if (!price) return;
                setPriceDraft(priceDraftFromEntry(price));
                setPriceError(null);
                setMode('price');
              }}
              onAddResource={(kind) => void media.addResource(kind)}
              onRemoveResource={(id) =>
                patchSelected({ attachments: selected.attachments.filter((row) => row.id !== id) })
              }
              onReplaceResource={(att) => void media.addResource(att.kind, att.id)}
              onEditCaption={(att) => media.editResource(att)}
              tr={tr}
            />
          </ScrollView>
          <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, 12) }]}>
            <PrimaryButton
              label={tr('servicesSave')}
              onPress={() => void handleSaveService()}
              loading={draft.saving}
              disabled={!draft.etag}
              style={styles.saveBtn}
            />
          </View>
        </KeyboardAvoidingView>
      ) : null}

      {!draft.loading && mode === 'price' && selected ? (
        <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <ScrollView contentContainerStyle={styles.editScroll} showsVerticalScrollIndicator={false}>
            <ServicePriceView
              draft={priceDraft}
              error={priceError}
              canDelete={Boolean(priceDraft.id)}
              onTitle={(title) => setPriceDraft((row) => ({ ...row, title }))}
              onAmount={(amountText) => setPriceDraft((row) => ({ ...row, amountText }))}
              onDetails={(details) => setPriceDraft((row) => ({ ...row, details }))}
              onDelete={deletePrice}
              tr={tr}
            />
          </ScrollView>
          <View style={[styles.priceFooter, { paddingBottom: Math.max(insets.bottom, 12) }]}>
            <PrimaryButton label={tr('servicesSavePrice')} onPress={() => upsertPrice(false)} style={styles.saveBtn} />
            <Pressable onPress={() => upsertPrice(true)} accessibilityRole="button">
              <Text style={styles.another}>{tr('servicesSaveAndAddAnother')}</Text>
            </Pressable>
          </View>
        </KeyboardAvoidingView>
      ) : null}

      <ResourceMetaModal
        visible={Boolean(media.prompt)}
        heading={media.prompt?.kind === 'link' ? tr('servicesLinkTitle') : tr('resourceMetaHeading')}
        preview={media.prompt?.preview}
        showUrl={media.prompt?.kind === 'link'}
        url={media.prompt?.url || ''}
        title={media.prompt?.title || ''}
        description={media.prompt?.description || ''}
        error={media.promptError}
        titleLabel={tr('resourceFieldTitle')}
        descriptionLabel={tr('resourceFieldDescription')}
        urlLabel={tr('servicesLinkTitle')}
        titlePlaceholder={tr('resourceTitlePlaceholder')}
        descriptionPlaceholder={tr('resourceDescriptionPlaceholder')}
        urlPlaceholder={tr('servicesLinkPlaceholder')}
        saveLabel={tr('aiSetupSave')}
        cancelLabel={tr('usersCancel')}
        onChangeUrl={(url) => media.setPrompt((row) => (row ? { ...row, url } : row))}
        onChangeTitle={(title) => media.setPrompt((row) => (row ? { ...row, title } : row))}
        onChangeDescription={(description) => media.setPrompt((row) => (row ? { ...row, description } : row))}
        onSave={media.commitPrompt}
        onClose={media.closePrompt}
      />
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  listScroll: { flexGrow: 1, paddingBottom: 16 },
  editScroll: { paddingBottom: 16 },
  error: { color: '#DC2626', fontFamily: fonts.body, marginBottom: 8 },
  warn: { color: '#D97706', fontFamily: fonts.body, marginBottom: 8 },
  footer: { paddingTop: 8 },
  priceFooter: { paddingTop: 8, gap: 10 },
  saveBtn: { backgroundColor: SV_TEAL, borderRadius: 12 },
  another: {
    color: SV_TEAL,
    fontFamily: fonts.bodyMedium,
    fontSize: 15,
    fontWeight: '700',
    textAlign: 'center',
    paddingVertical: 6,
  },
});
