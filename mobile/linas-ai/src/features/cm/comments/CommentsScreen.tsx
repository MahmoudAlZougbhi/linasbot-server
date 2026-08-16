import { useEffect, useMemo, useState } from 'react';
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
import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { ScreenChrome } from '../../shared/ScreenChrome';
import { asRecordList, newId } from '../cmApi';
import type { CmProposalReview } from '../cmProposalReview';
import { useCmDraft } from '../useCmDraft';
import { CommentEditView } from './CommentEditView';
import { CommentListView } from './CommentListView';
import { CommentPostsView } from './CommentPostsView';
import { CommentTextModal } from './CommentTextModal';
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
  uniquePostIds,
  type CommentRuleItem,
} from './commentModel';
import {
  fetchCommentAccounts,
  fetchConnectedPosts,
  type CommentAccount,
  type ConnectedPost,
} from './commentPostsApi';
import { useCommentMedia } from './useCommentMedia';

type Props = {
  proposalReview?: CmProposalReview | null;
  onBack?: () => void;
};

type Mode = 'list' | 'edit' | 'posts';

function postsErrorMessage(code: string, tr: (key: StringKey) => string): string {
  if (code === 'graph_permission_denied' || code === 'credential_unavailable') return tr('commentsGraphDenied');
  if (code === 'account_not_in_tenant' || code === 'account_id_missing') return tr('commentsNoAccount');
  return tr('commentsGraphFailed');
}

export function CommentsScreen({ proposalReview, onBack }: Props) {
  const { tr } = useI18n();
  const insets = useSafeAreaInsets();
  const draft = useCmDraft('comments', proposalReview);
  const [mode, setMode] = useState<Mode>('list');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<CommentAccount[]>([]);
  const [posts, setPosts] = useState<ConnectedPost[]>([]);
  const [postQuery, setPostQuery] = useState('');
  const [postError, setPostError] = useState<string | null>(null);
  const [postsLoading, setPostsLoading] = useState(false);
  const [nextAfter, setNextAfter] = useState('');
  const [allowManual, setAllowManual] = useState(true);
  const [manualId, setManualId] = useState('');
  const [draftSelected, setDraftSelected] = useState<string[]>([]);
  const [accountId, setAccountId] = useState('');

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

  useEffect(() => {
    void fetchCommentAccounts()
      .then((rows) => {
        setAccounts(rows);
        if (rows[0] && !accountId) setAccountId(rows[0].connected_account_id);
      })
      .catch(() => setAccounts([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  async function loadPosts(nextAccount: CommentAccount | undefined, after = '', append = false) {
    if (!nextAccount) {
      setPosts([]);
      setPostError(tr('commentsNoAccount'));
      setAllowManual(true);
      return;
    }
    setPostsLoading(true);
    if (!append) setPostError(null);
    try {
      const result = await fetchConnectedPosts({
        platform: nextAccount.platform,
        connectedAccountId: nextAccount.connected_account_id,
        after,
      });
      setPosts((current) => (append ? [...current, ...result.posts] : result.posts));
      setNextAfter(result.nextAfter);
      setAllowManual(result.allowManual);
      if (!result.ok) setPostError(postsErrorMessage(result.error, tr));
    } catch {
      setPosts(append ? posts : []);
      setAllowManual(true);
      setPostError(tr('commentsGraphFailed'));
    } finally {
      setPostsLoading(false);
    }
  }

  function openPostsPicker() {
    if (!selected) return;
    const currentAccount =
      accounts.find((row) => row.connected_account_id === (selected.connected_account_id || accountId)) || accounts[0];
    if (currentAccount) setAccountId(currentAccount.connected_account_id);
    setDraftSelected(uniquePostIds(selected));
    setPostQuery('');
    setManualId('');
    setMode('posts');
    void loadPosts(currentAccount);
  }

  function confirmPosts() {
    if (!selected) return;
    const account = accounts.find((row) => row.connected_account_id === accountId);
    const first = posts.find((post) => post.id === draftSelected[0]);
    patchSelected(
      applySelectedPosts(selected, draftSelected, {
        permalink: first?.permalink,
        caption: first?.preview,
        platform: account?.platform,
        accountId: account?.connected_account_id,
        pageId: account?.page_or_ig_account_id,
      }),
    );
    setMode('edit');
  }

  const chromeTitle = mode === 'list' ? ' ' : tr('aiSetupSec_comments');

  return (
    <ScreenChrome
      title={chromeTitle}
      hideTitle={mode === 'list'}
      onBack={mode === 'list' ? onBack : mode === 'posts' ? () => setMode('edit') : goList}
      canvasColor={CM_CANVAS}
    >
      {draft.loading ? <LinasLoadingIndicator variant="screen" /> : null}
      {draft.error ? <Text style={styles.error}>{draft.error}</Text> : null}
      {draft.conflict ? <Text style={styles.warn}>{draft.conflict}</Text> : null}
      {draft.proposalActive ? <Text style={styles.warn}>{tr('commentsProposalPreview')}</Text> : null}

      {!draft.loading && mode === 'list' ? (
        <ScrollView contentContainerStyle={styles.listScroll} showsVerticalScrollIndicator={false}>
          <CommentListView
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
              onEditCaption={(att) => {
                media.setPrompt({ kind: 'caption', attachId: att.id });
                media.setPromptValue(att.caption);
              }}
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
        <ScrollView contentContainerStyle={styles.editScroll} showsVerticalScrollIndicator={false}>
          <CommentPostsView
            posts={posts}
            selectedIds={draftSelected}
            query={postQuery}
            loading={postsLoading}
            error={postError}
            allowManual={allowManual}
            manualId={manualId}
            nextAfter={nextAfter}
            accounts={accounts}
            accountId={accountId}
            onAccount={(id) => {
              setAccountId(id);
              const account = accounts.find((row) => row.connected_account_id === id);
              void loadPosts(account);
            }}
            onQueryChange={setPostQuery}
            onToggle={(id) =>
              setDraftSelected((current) =>
                current.includes(id) ? current.filter((row) => row !== id) : [...current, id],
              )
            }
            onManualId={setManualId}
            onAddManual={() => {
              const id = manualId.trim();
              if (!id) return;
              setDraftSelected((current) => (current.includes(id) ? current : [...current, id]));
              setManualId('');
            }}
            onLoadMore={() => {
              const account = accounts.find((row) => row.connected_account_id === accountId);
              void loadPosts(account, nextAfter, true);
            }}
            onConfirm={confirmPosts}
            tr={tr}
          />
        </ScrollView>
      ) : null}

      <CommentTextModal
        visible={Boolean(media.prompt)}
        title={media.prompt?.kind === 'caption' ? tr('commentsEditCaption') : tr('commentsLinkTitle')}
        value={media.promptValue}
        placeholder={media.prompt?.kind === 'caption' ? tr('commentsCaption') : tr('commentsLinkPlaceholder')}
        keyboardType={media.prompt?.kind === 'link' ? 'url' : 'default'}
        saveLabel={tr('commentsSave')}
        cancelLabel={tr('usersCancel')}
        onChange={media.setPromptValue}
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
  pressed: { opacity: 0.7 },
});
