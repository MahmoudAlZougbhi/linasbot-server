import { useMemo, useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppIcon, feather } from '../../../components/AppIcon';
import { LinasLoadingIndicator } from '../../../components/LinasLoadingIndicator';
import { PrimaryButton } from '../../../components/PrimaryButton';
import { useI18n } from '../../../i18n/LanguageContext';
import { fonts } from '../../../theme';
import { ScreenChrome } from '../../shared/ScreenChrome';
import { asRecordList, newId } from '../cmApi';
import type { CmProposalReview } from '../cmProposalReview';
import { ResourceMetaModal } from '../resources/ResourceMetaModal';
import { moveById } from '../resources/resourceMeta';
import { useCmDraft } from '../useCmDraft';
import { KnowledgeEditView } from './KnowledgeEditView';
import { KnowledgeListView } from './KnowledgeListView';
import { KN_CANVAS, KN_TEAL } from './knowledgeChrome';
import {
  buildKnowledgeList,
  createKnowledgeItem,
  itemToRecord,
  parseKnowledgeItem,
  togglePublishedStatus,
  touchUpdated,
  type KnowledgeItem,
} from './knowledgeModel';
import { useKnowledgeMedia } from './useKnowledgeMedia';

type Props = {
  proposalReview?: CmProposalReview | null;
  onBack?: () => void;
  onOpenLocations?: () => void;
};

export function KnowledgeScreen({ proposalReview, onBack, onOpenLocations }: Props) {
  const { tr } = useI18n();
  const insets = useSafeAreaInsets();
  const draft = useCmDraft('knowledge', proposalReview);
  const [mode, setMode] = useState<'list' | 'edit'>('list');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  const items = useMemo(
    () => asRecordList(draft.payload.items).map(parseKnowledgeItem),
    [draft.payload.items],
  );
  const selected = items.find((item) => item.id === selectedId) || null;
  const rows = useMemo(() => buildKnowledgeList(items, query), [items, query]);

  function setItems(next: KnowledgeItem[]) {
    draft.setPayload({ ...draft.payload, items: next.map(itemToRecord) });
  }

  function patchSelected(patch: Partial<KnowledgeItem>) {
    if (!selected) return;
    const now = new Date().toISOString();
    setItems(items.map((item) => (item.id === selected.id ? touchUpdated({ ...item, ...patch }, now) : item)));
  }

  const media = useKnowledgeMedia(selected, patchSelected, tr);

  function handleAdd() {
    const item = createKnowledgeItem(newId('knowledge'), new Date().toISOString());
    setItems([item, ...items]);
    setSelectedId(item.id);
    setMode('edit');
  }

  function goList() {
    setMode('list');
    setSelectedId(null);
    media.setUploadError(null);
  }

  async function handleSave() {
    await draft.save();
  }

  async function handleDelete() {
    if (!selected) return;
    const nextPayload = {
      ...draft.payload,
      items: items.filter((item) => item.id !== selected.id).map(itemToRecord),
    };
    const ok = await draft.save(nextPayload);
    if (ok) goList();
  }

  function confirmDelete() {
    if (!selected) return;
    Alert.alert(tr('knowledgeDeleteTitle'), tr('knowledgeDeleteBody'), [
      { text: tr('usersCancel'), style: 'cancel' },
      {
        text: tr('knowledgeDeleteConfirm'),
        style: 'destructive',
        onPress: () => void handleDelete(),
      },
    ]);
  }

  return (
    <ScreenChrome
      title={tr('aiSetupSec_knowledge')}
      subtitle={mode === 'list' ? tr('knowledgeSubtitle') : undefined}
      onBack={mode === 'edit' ? goList : onBack}
      canvasColor={KN_CANVAS}
    >
      {draft.loading ? <LinasLoadingIndicator variant="screen" /> : null}
      {draft.error ? <Text style={styles.error}>{draft.error}</Text> : null}
      {draft.conflict ? <Text style={styles.warn}>{draft.conflict}</Text> : null}
      {draft.proposalActive ? (
        <Text style={styles.warn}>{tr('knowledgeProposalPreview')}</Text>
      ) : null}

      {!draft.loading && mode === 'list' ? (
        <ScrollView contentContainerStyle={styles.listScroll} showsVerticalScrollIndicator={false}>
          <KnowledgeListView
            rows={rows}
            query={query}
            count={rows.length}
            onQueryChange={setQuery}
            onAdd={handleAdd}
            onSelect={(id) => {
              setSelectedId(id);
              setMode('edit');
            }}
            onOpenLocations={() => onOpenLocations?.()}
            tr={tr}
          />
        </ScrollView>
      ) : null}

      {!draft.loading && mode === 'edit' && selected ? (
        <KeyboardAvoidingView
          style={styles.flex}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          <ScrollView contentContainerStyle={styles.editScroll} showsVerticalScrollIndicator={false}>
            <KnowledgeEditView
              item={selected}
              uploading={media.uploading}
              uploadError={media.uploadError}
              onTitle={(title) => patchSelected({ title })}
              onBody={(body) => patchSelected({ body })}
              onTogglePublished={() => patchSelected({ status: togglePublishedStatus(selected.status) })}
              onAddResource={(kind) => void media.addResource(kind)}
              onRemoveResource={(id) =>
                patchSelected({ attachments: selected.attachments.filter((row) => row.id !== id) })
              }
              onReplaceResource={(att) => void media.addResource(att.kind, att.id)}
              onEditCaption={media.editResource}
              onMoveResource={(id, direction) =>
                patchSelected({ attachments: moveById(selected.attachments, id, direction) })
              }
              tr={tr}
            />
          </ScrollView>
          <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, 12) }]}>
            <Pressable
              onPress={confirmDelete}
              accessibilityRole="button"
              accessibilityLabel={tr('knowledgeDelete')}
              style={({ pressed }) => [styles.deleteBtn, pressed && styles.pressed]}
            >
              <AppIcon icon={feather('trash-2')} size={18} color="#DC2626" />
              <Text style={styles.deleteText}>{tr('knowledgeDelete')}</Text>
            </Pressable>
            <PrimaryButton
              label={tr('aiSetupSave')}
              onPress={() => void handleSave()}
              loading={draft.saving}
              disabled={!draft.dirty || !draft.etag}
              style={styles.saveBtn}
            />
          </View>
        </KeyboardAvoidingView>
      ) : null}

      <ResourceMetaModal
        visible={Boolean(media.prompt)}
        heading={media.prompt?.kind === 'link' ? tr('knowledgeLinkTitle') : tr('resourceMetaHeading')}
        preview={media.prompt?.preview}
        showUrl={media.prompt?.kind === 'link'}
        url={media.prompt?.url || ''}
        title={media.prompt?.title || ''}
        description={media.prompt?.description || ''}
        error={media.promptError}
        titleLabel={tr('resourceFieldTitle')}
        descriptionLabel={tr('resourceFieldDescription')}
        urlLabel={tr('knowledgeLinkTitle')}
        titlePlaceholder={tr('resourceTitlePlaceholder')}
        descriptionPlaceholder={tr('resourceDescriptionPlaceholder')}
        urlPlaceholder={tr('knowledgeLinkPlaceholder')}
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
  pressed: { opacity: 0.7 },
  error: { color: '#DC2626', fontFamily: fonts.body, marginBottom: 8 },
  warn: { color: '#D97706', fontFamily: fonts.body, marginBottom: 8 },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingTop: 8,
  },
  deleteBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderWidth: 1.5,
    borderColor: '#DC2626',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    minWidth: 108,
  },
  deleteText: { color: '#DC2626', fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
  saveBtn: { flex: 1, backgroundColor: KN_TEAL, borderRadius: 12 },
});
