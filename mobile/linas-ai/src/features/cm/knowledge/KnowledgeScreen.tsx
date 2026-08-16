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

import { ApiError } from '../../../api/client';
import { AppIcon, feather } from '../../../components/AppIcon';
import { LinasLoadingIndicator } from '../../../components/LinasLoadingIndicator';
import { PrimaryButton } from '../../../components/PrimaryButton';
import { useI18n } from '../../../i18n/LanguageContext';
import { fonts } from '../../../theme';
import { ScreenChrome } from '../../shared/ScreenChrome';
import { asRecordList, newId } from '../cmApi';
import { uploadCmArticleMedia } from '../cmMediaApi';
import type { CmProposalReview } from '../cmProposalReview';
import { useCmDraft } from '../useCmDraft';
import { KnowledgeEditView } from './KnowledgeEditView';
import { KnowledgeListView } from './KnowledgeListView';
import { KN_CANVAS, KN_TEAL } from './knowledgeChrome';
import {
  buildKnowledgeList,
  createKnowledgeItem,
  isValidHttpUrl,
  itemToRecord,
  parseKnowledgeItem,
  togglePublishedStatus,
  touchUpdated,
  type KnowledgeAttachment,
  type KnowledgeItem,
  type KnowledgeKind,
} from './knowledgeModel';
import { pickKnowledgeFile, pickKnowledgeImage, pickKnowledgeVideo } from './knowledgePick';
import { ResourceMetaModal } from '../resources/ResourceMetaModal';
import {
  moveById,
  resourceMetaError,
  serializeResourceFields,
  suggestedTitleFromFilename,
} from '../resources/resourceMeta';

type Props = {
  proposalReview?: CmProposalReview | null;
  onBack?: () => void;
  onOpenLocations?: () => void;
};

type ResourcePrompt = {
  mode: 'create' | 'edit';
  kind: KnowledgeKind;
  attachId?: string;
  replaceId?: string;
  preview: string;
  url: string;
  title: string;
  description: string;
  pending?: KnowledgeAttachment;
};

export function KnowledgeScreen({ proposalReview, onBack, onOpenLocations }: Props) {
  const { tr } = useI18n();
  const insets = useSafeAreaInsets();
  const draft = useCmDraft('knowledge', proposalReview);
  const [mode, setMode] = useState<'list' | 'edit'>('list');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [prompt, setPrompt] = useState<ResourcePrompt | null>(null);
  const [promptError, setPromptError] = useState<string | null>(null);

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

  function handleAdd() {
    const item = createKnowledgeItem(newId('knowledge'), new Date().toISOString());
    setItems([item, ...items]);
    setSelectedId(item.id);
    setMode('edit');
  }

  function goList() {
    setMode('list');
    setSelectedId(null);
    setUploadError(null);
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

  function uploadFailMessage(err: unknown): string {
    const detail =
      err instanceof ApiError && err.body && typeof err.body === 'object' && 'detail' in err.body
        ? JSON.stringify((err.body as { detail: unknown }).detail)
        : err instanceof Error
          ? err.message
          : '';
    if (detail.includes('file_too_large')) return tr('knowledgeVideoTooLarge');
    if (detail.includes('unsupported_mime')) return tr('knowledgeUnsupported');
    return tr('knowledgeUploadFailed');
  }

  async function attachPicked(
    picked: { uri: string; name: string; mimeType: string; durationSeconds?: number } | null,
    kind: KnowledgeKind,
    replaceId?: string,
  ) {
    if (!selected || !picked) return;
    setUploading(true);
    setUploadError(null);
    try {
      const uploaded = await uploadCmArticleMedia(picked);
      const nextAtt: KnowledgeAttachment = {
        id: uploaded.media_id,
        kind: uploaded.kind === 'image' || uploaded.kind === 'video' ? uploaded.kind : kind === 'video' ? 'video' : kind === 'image' ? 'image' : 'file',
        title: '',
        description: '',
        caption: '',
        mime: uploaded.mime || picked.mimeType,
        filename: uploaded.filename || picked.name,
        size: uploaded.size || 0,
        url: '',
        duration_seconds: picked.durationSeconds ?? null,
      };
      const existing = replaceId ? selected.attachments.find((row) => row.id === replaceId) : null;
      setPrompt({
        mode: replaceId ? 'edit' : 'create',
        kind: nextAtt.kind,
        replaceId,
        attachId: replaceId,
        preview: nextAtt.filename,
        url: '',
        title: existing?.title || suggestedTitleFromFilename(nextAtt.filename),
        description: existing?.description || existing?.caption || '',
        pending: nextAtt,
      });
      setPromptError(null);
    } catch (err) {
      setUploadError(uploadFailMessage(err));
    } finally {
      setUploading(false);
    }
  }

  async function handleAddResource(kind: KnowledgeKind, replaceId?: string) {
    if (kind === 'link') {
      const existing = replaceId ? selected?.attachments.find((row) => row.id === replaceId) : null;
      setPrompt({
        mode: replaceId ? 'edit' : 'create',
        kind: 'link',
        replaceId,
        attachId: replaceId,
        preview: existing?.filename || '',
        url: existing?.url || '',
        title: existing?.title || '',
        description: existing?.description || existing?.caption || '',
      });
      setPromptError(null);
      return;
    }
    if (kind === 'image') {
      const picked = await pickKnowledgeImage();
      await attachPicked(picked, 'image', replaceId);
      return;
    }
    if (kind === 'video') {
      const picked = await pickKnowledgeVideo();
      await attachPicked(picked, 'video', replaceId);
      return;
    }
    const picked = await pickKnowledgeFile();
    await attachPicked(picked, 'file', replaceId);
  }

  function handleReplace(att: KnowledgeAttachment) {
    void handleAddResource(att.kind, att.id);
  }

  function handleEditResource(att: KnowledgeAttachment) {
    setPrompt({
      mode: 'edit',
      kind: att.kind,
      attachId: att.id,
      preview: att.filename || att.url,
      url: att.url,
      title: att.title,
      description: att.description || att.caption,
    });
    setPromptError(null);
  }

  function commitPrompt() {
    if (!selected || !prompt) return;
    const err = resourceMetaError(prompt.kind, { title: prompt.title, description: prompt.description }, prompt.url);
    if (err === 'title') {
      setPromptError(tr('resourceTitleRequired'));
      return;
    }
    if (err === 'description') {
      setPromptError(tr('resourceDescriptionRequired'));
      return;
    }
    if (err === 'url' || (prompt.kind === 'link' && !isValidHttpUrl(prompt.url))) {
      setPromptError(tr('knowledgeLinkInvalid'));
      return;
    }
    const meta = serializeResourceFields({ title: prompt.title, description: prompt.description });
    if (prompt.kind === 'link') {
      const url = prompt.url.trim();
      let host = url;
      try {
        host = new URL(url).hostname;
      } catch {
        host = url;
      }
      const nextAtt: KnowledgeAttachment = {
        id: prompt.replaceId || prompt.attachId || newId('link'),
        kind: 'link',
        title: meta.title,
        description: meta.description,
        caption: meta.caption,
        mime: '',
        filename: host,
        size: 0,
        url,
        duration_seconds: null,
      };
      const current = selected.attachments;
      const next = prompt.replaceId || prompt.attachId
        ? current.map((row) => (row.id === (prompt.replaceId || prompt.attachId) ? nextAtt : row))
        : [...current, nextAtt];
      patchSelected({ attachments: next });
      setPrompt(null);
      setPromptError(null);
      setUploadError(null);
      return;
    }
    if (prompt.pending) {
      const nextAtt: KnowledgeAttachment = { ...prompt.pending, ...meta };
      const current = selected.attachments;
      const next = prompt.replaceId
        ? current.map((row) => (row.id === prompt.replaceId ? { ...nextAtt, id: row.id } : row))
        : [...current, nextAtt];
      patchSelected({ attachments: next });
      setPrompt(null);
      setPromptError(null);
      return;
    }
    if (!prompt.attachId) return;
    patchSelected({
      attachments: selected.attachments.map((row) =>
        row.id === prompt.attachId ? { ...row, ...meta } : row,
      ),
    });
    setPrompt(null);
    setPromptError(null);
  }

  const addPill = (
    <Pressable
      onPress={handleAdd}
      accessibilityRole="button"
      accessibilityLabel={tr('knowledgeAdd')}
      style={({ pressed }) => [styles.addPill, pressed && styles.pressed]}
    >
      <Text style={styles.addPillText}>{tr('knowledgeAdd')}</Text>
    </Pressable>
  );

  return (
    <ScreenChrome
      title={mode === 'edit' ? tr('aiSetupSec_knowledge') : ' '}
      onBack={mode === 'edit' ? goList : onBack}
      headerRight={mode === 'list' ? addPill : undefined}
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
              uploading={uploading}
              uploadError={uploadError}
              onTitle={(title) => patchSelected({ title })}
              onBody={(body) => patchSelected({ body })}
              onTogglePublished={() => patchSelected({ status: togglePublishedStatus(selected.status) })}
              onAddResource={(kind) => void handleAddResource(kind)}
              onRemoveResource={(id) =>
                patchSelected({ attachments: selected.attachments.filter((row) => row.id !== id) })
              }
              onReplaceResource={handleReplace}
              onEditCaption={handleEditResource}
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
              label={tr('knowledgeSave')}
              onPress={() => void handleSave()}
              loading={draft.saving}
              disabled={!draft.dirty || !draft.etag}
              style={styles.saveBtn}
            />
          </View>
        </KeyboardAvoidingView>
      ) : null}

      <ResourceMetaModal
        visible={Boolean(prompt)}
        heading={prompt?.kind === 'link' ? tr('knowledgeLinkTitle') : tr('resourceMetaHeading')}
        preview={prompt?.preview}
        showUrl={prompt?.kind === 'link'}
        url={prompt?.url || ''}
        title={prompt?.title || ''}
        description={prompt?.description || ''}
        error={promptError}
        titleLabel={tr('resourceFieldTitle')}
        descriptionLabel={tr('resourceFieldDescription')}
        urlLabel={tr('knowledgeLinkTitle')}
        titlePlaceholder={tr('resourceTitlePlaceholder')}
        descriptionPlaceholder={tr('resourceDescriptionPlaceholder')}
        urlPlaceholder={tr('knowledgeLinkPlaceholder')}
        saveLabel={tr('knowledgeSave')}
        cancelLabel={tr('usersCancel')}
        onChangeUrl={(url) => setPrompt((row) => (row ? { ...row, url } : row))}
        onChangeTitle={(title) => setPrompt((row) => (row ? { ...row, title } : row))}
        onChangeDescription={(description) => setPrompt((row) => (row ? { ...row, description } : row))}
        onSave={commitPrompt}
        onClose={() => {
          setPrompt(null);
          setPromptError(null);
        }}
      />
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  listScroll: { flexGrow: 1, paddingBottom: 16 },
  editScroll: { paddingBottom: 16 },
  addPill: {
    backgroundColor: KN_TEAL,
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  addPillText: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '700' },
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
