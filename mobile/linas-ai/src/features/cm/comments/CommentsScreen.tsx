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
import { useCmDraft } from '../useCmDraft';
import { CommentEditView } from './CommentEditView';
import { CommentRulePostsPicker } from './CommentRulePostsPicker';
import { CommentsListPanel } from './CommentsListPanel';
import { CM_CANVAS, CM_TEAL } from './commentChrome';
import {
  applyPostsMode,
  applyReplyIn,
  applyReplyType,
  applySelectedPosts,
  createCommentRule,
  matchesCommentQuery,
  parseCommentRule,
  parseKeywords,
  replyInOf,
  ruleToRecord,
  selectedPostsOf,
  uniquePostIds,
  type CommentRuleItem,
} from './commentModel';
import type { SelectedCommentPost } from './commentPostSnapshots';
import { useCommentMedia } from './useCommentMedia';

type Props = {
  proposalReview?: CmProposalReview | null;
  onBack?: () => void;
};

type Mode = 'list' | 'edit' | 'posts';

export function CommentsScreen({ proposalReview, onBack }: Props) {
  const { tr } = useI18n();
  const insets = useSafeAreaInsets();
  const draft = useCmDraft('comments', proposalReview);
  const [mode, setMode] = useState<Mode>('list');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [picked, setPicked] = useState<SelectedCommentPost[]>([]);

  const items = useMemo(
    () => asRecordList(draft.payload.rules).map(parseCommentRule),
    [draft.payload.rules],
  );
  const selected = items.find((item) => item.id === selectedId) || null;
  const visible = useMemo(
    () => items.filter((item) => matchesCommentQuery(item, query)),
    [items, query],
  );

  function setRules(next: CommentRuleItem[]) {
    draft.setPayload({ ...draft.payload, rules: next.map(ruleToRecord) });
  }

  function patchSelected(patch: Partial<CommentRuleItem>) {
    if (!selected) return;
    setRules(items.map((item) => (item.id === selected.id ? { ...item, ...patch } : item)));
  }

  const media = useCommentMedia(selected, patchSelected, tr);

  function handleAdd() {
    const item = createCommentRule(newId('crule'));
    setRules([item, ...items]);
    setSelectedId(item.id);
    setMode('edit');
    media.setUploadError(null);
    setSaveError(null);
  }

  function goList() {
    if (selected && !selected.name.trim() && !selected.reply_template.trim() && !selected.ai_instructions.trim()) {
      setRules(items.filter((item) => item.id !== selected.id));
    }
    setMode('list');
    setSelectedId(null);
    media.setUploadError(null);
    setSaveError(null);
  }

  async function handleSave() {
    if (!selected?.name.trim()) {
      setSaveError(tr('commentsNameRequired'));
      return;
    }
    if (selected.scope === 'specific_post' && uniquePostIds(selected).length < 1) {
      setSaveError(tr('commentsPostsRequired'));
      return;
    }
    const ok = await draft.save();
    if (ok) goList();
  }

  function confirmDelete() {
    if (!selected) return;
    Alert.alert(tr('commentsDeleteTitle'), tr('commentsDeleteBody'), [
      { text: tr('usersCancel'), style: 'cancel' },
      {
        text: tr('commentsDelete'),
        style: 'destructive',
        onPress: () => {
          const next = { ...draft.payload, rules: items.filter((item) => item.id !== selected.id).map(ruleToRecord) };
          void draft.save(next).then((ok) => {
            if (ok) goList();
          });
        },
      },
    ]);
  }

  function openPostsPicker() {
    if (!selected) return;
    setPicked(selectedPostsOf(selected));
    setMode('posts');
  }

  function confirmPosts() {
    if (!selected) return;
    patchSelected(applySelectedPosts(selected, picked));
    setMode('edit');
  }

  return (
    <ScreenChrome
      title={mode === 'posts' ? tr('commentsChoosePosts') : tr('aiSetupSec_comments')}
      subtitle={mode === 'list' ? tr('commentsSubtitle') : undefined}
      onBack={mode === 'list' ? onBack : mode === 'posts' ? () => setMode('edit') : goList}
      canvasColor={CM_CANVAS}
      headerRight={
        mode === 'posts' && picked.length ? (
          <Pressable
            onPress={confirmPosts}
            accessibilityRole="button"
            accessibilityLabel={tr('commentsPickerSave')}
            style={({ pressed }) => [styles.headerSave, pressed && styles.pressed]}
          >
            <Text style={styles.headerSaveText}>{tr('commentsPickerSave')}</Text>
          </Pressable>
        ) : undefined
      }
    >
      {draft.loading ? <LinasLoadingIndicator variant="screen" /> : null}
      {draft.error ? <Text style={styles.error}>{draft.error}</Text> : null}
      {draft.conflict ? <Text style={styles.warn}>{draft.conflict}</Text> : null}
      {draft.proposalActive ? <Text style={styles.warn}>{tr('commentsProposalPreview')}</Text> : null}

      {!draft.loading && mode === 'list' ? (
        <CommentsListPanel
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
      ) : null}

      {!draft.loading && mode === 'edit' && selected ? (
        <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <ScrollView contentContainerStyle={styles.editScroll} showsVerticalScrollIndicator={false}>
            {saveError ? <Text style={styles.error}>{saveError}</Text> : null}
            <CommentEditView
              item={selected}
              uploading={media.uploading}
              uploadError={media.uploadError}
              onTitle={(name) => patchSelected({ name })}
              onReplyType={(type) => patchSelected(applyReplyType(selected, type))}
              onPostsMode={(modeValue) => {
                patchSelected(applyPostsMode(selected, modeValue));
                if (modeValue === 'choose') openPostsPicker();
              }}
              onChoosePosts={openPostsPicker}
              onReplyIn={(replyIn) => patchSelected(applyReplyIn(selected, replyIn))}
              onKeywords={(value) => patchSelected({ keywords: parseKeywords(value) })}
              onReplyMessage={(reply_template) =>
                patchSelected({
                  reply_template,
                  dm_template: replyInOf(selected) === 'comment' ? '' : reply_template,
                })
              }
              onNote={(ai_instructions) => patchSelected({ ai_instructions })}
              onToggleActive={() => patchSelected({ enabled: !selected.enabled })}
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
            <Pressable
              onPress={confirmDelete}
              accessibilityRole="button"
              accessibilityLabel={tr('commentsDelete')}
              style={({ pressed }) => [styles.deleteBtn, pressed && styles.pressed]}
            >
              <AppIcon icon={feather('trash-2')} size={18} color="#DC2626" />
              <Text style={styles.deleteText}>{tr('commentsDelete')}</Text>
            </Pressable>
            <PrimaryButton
              label={tr('commentsSave')}
              onPress={() => void handleSave()}
              loading={draft.saving}
              disabled={!draft.etag}
              style={styles.saveBtn}
            />
          </View>
        </KeyboardAvoidingView>
      ) : null}

      {!draft.loading && mode === 'posts' ? (
        <CommentRulePostsPicker selected={picked} onChange={setPicked} tr={tr} />
      ) : null}

      <ResourceMetaModal
        visible={Boolean(media.prompt)}
        heading={media.prompt?.kind === 'link' ? tr('commentsLinkTitle') : tr('resourceMetaHeading')}
        preview={media.prompt?.preview}
        showUrl={media.prompt?.kind === 'link'}
        url={media.prompt?.url || ''}
        title={media.prompt?.title || ''}
        description={media.prompt?.description || ''}
        error={media.promptError}
        titleLabel={tr('resourceFieldTitle')}
        descriptionLabel={tr('resourceFieldDescription')}
        urlLabel={tr('commentsLinkTitle')}
        titlePlaceholder={tr('resourceTitlePlaceholder')}
        descriptionPlaceholder={tr('resourceDescriptionPlaceholder')}
        urlPlaceholder={tr('commentsLinkPlaceholder')}
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
  editScroll: { paddingBottom: 16 },
  error: { color: '#DC2626', fontFamily: fonts.body, marginBottom: 8 },
  warn: { color: '#D97706', fontFamily: fonts.body, marginBottom: 8 },
  footer: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingTop: 8 },
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
  saveBtn: { flex: 1, backgroundColor: CM_TEAL, borderRadius: 12 },
  headerSave: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 4 },
  headerSaveText: { color: CM_TEAL, fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  pressed: { opacity: 0.7 },
});
