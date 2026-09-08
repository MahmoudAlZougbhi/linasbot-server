import { ActivityIndicator, StyleSheet, Text, TextInput, View } from 'react-native';

import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { ClampedLongField } from '../ClampedLongField';
import { CM_BORDER, CM_MUTED, CM_RADIUS, CM_TEAL, CM_TEAL_DARK } from './commentChrome';
import { CommentSelectedPosts } from './CommentSelectedPosts';
import {
  postsModeOf,
  replyInOf,
  replyTypeOf,
  selectedPostsOf,
  type CommentAttachment,
  type CommentKind,
  type CommentPostsMode,
  type CommentReplyIn,
  type CommentReplyType,
  type CommentRuleItem,
} from './commentModel';
import { CommentResourceGrid, CommentResourceRows } from './CommentResources';
import { CommentSegmented } from './CommentSegmented';

type Props = {
  item: CommentRuleItem;
  uploading: boolean;
  uploadError: string | null;
  onTitle: (value: string) => void;
  onReplyType: (value: CommentReplyType) => void;
  onPostsMode: (value: CommentPostsMode) => void;
  onChoosePosts: () => void;
  onReplyIn: (value: CommentReplyIn) => void;
  onKeywords: (value: string) => void;
  onReplyMessage: (value: string) => void;
  onNote: (value: string) => void;
  onAddResource: (kind: CommentKind) => void;
  onRemoveResource: (id: string) => void;
  onReplaceResource: (att: CommentAttachment) => void;
  onEditCaption: (att: CommentAttachment) => void;
  tr: (key: StringKey) => string;
};

export function CommentEditView({
  item,
  uploading,
  uploadError,
  onTitle,
  onReplyType,
  onPostsMode,
  onChoosePosts,
  onReplyIn,
  onKeywords,
  onReplyMessage,
  onNote,
  onAddResource,
  onRemoveResource,
  onReplaceResource,
  onEditCaption,
  tr,
}: Props) {
  const isAi = replyTypeOf(item) === 'ai';
  const replyIn = replyInOf(item);
  const postsMode = postsModeOf(item);

  return (
    <View style={styles.wrap}>
      <Text style={styles.hero}>{tr(isAi ? 'commentsEditAi' : 'commentsEditAutomatic')}</Text>

      <View style={styles.box}>
        <Text style={styles.boxLabel}>{tr('commentsFieldTitle')}</Text>
        <TextInput
          value={item.name}
          onChangeText={onTitle}
          style={styles.input}
          placeholder={tr('commentsUntitled')}
          placeholderTextColor={CM_MUTED}
        />
        {isAi ? (
          <ClampedLongField
            label={tr('commentsNote')}
            value={item.ai_instructions}
            onChange={onNote}
            placeholder={tr('commentsNote')}
            placeholderTextColor={CM_MUTED}
            hint={tr('commentsNoteHint')}
            labelStyle={styles.label}
            inputStyle={styles.input}
            hintStyle={styles.hint}
          />
        ) : null}
      </View>

      <CommentSegmented
        label={tr('commentsReplyType')}
        value={isAi ? 'ai' : 'automatic'}
        options={[
          { id: 'automatic', label: tr('commentsTypeAutomatic') },
          { id: 'ai', label: tr('commentsTypeAi') },
        ]}
        onChange={onReplyType}
      />
      <CommentSegmented
        label={tr('commentsPosts')}
        value={postsMode}
        options={[
          { id: 'all', label: tr('commentsAllPosts') },
          { id: 'choose', label: tr('commentsChoosePosts') },
        ]}
        onChange={(mode) => {
          onPostsMode(mode);
          if (mode === 'choose') onChoosePosts();
        }}
      />
      {postsMode === 'choose' ? <CommentSelectedPosts posts={selectedPostsOf(item)} onPress={onChoosePosts} /> : null}
      <CommentSegmented
        label={tr('commentsReplyIn')}
        value={replyIn}
        options={[
          { id: 'comment', label: tr('commentsReplyComment') },
          { id: 'dm', label: tr('commentsReplyDm') },
          { id: 'both', label: tr('commentsReplyBoth') },
        ]}
        onChange={onReplyIn}
      />

      {isAi ? null : (
        <>
          <Text style={styles.label}>{tr('commentsKeywords')}</Text>
          <TextInput
            value={item.keywords.join(', ')}
            onChangeText={onKeywords}
            style={styles.input}
            placeholder={tr('commentsKeywordsPlaceholder')}
            placeholderTextColor={CM_MUTED}
            autoCapitalize="none"
          />
          <ClampedLongField
            label={tr('commentsReplyMessage')}
            value={item.reply_template}
            onChange={onReplyMessage}
            placeholderTextColor={CM_MUTED}
            labelStyle={styles.label}
            inputStyle={styles.input}
          />
        </>
      )}

      <Text style={styles.section}>{tr('commentsResources')}</Text>
      <Text style={styles.hint}>{tr(isAi ? 'commentsResourcesAiHint' : 'commentsResourcesAutoHint')}</Text>
      <CommentResourceGrid replyIn={replyIn} disabled={uploading} onAdd={onAddResource} tr={tr} />
      {uploading ? <ActivityIndicator color={CM_TEAL} style={styles.upload} /> : null}
      {uploadError ? <Text style={styles.error}>{uploadError}</Text> : null}
      <CommentResourceRows
        attachments={item.attachments}
        onRemove={onRemoveResource}
        onReplace={onReplaceResource}
        onEditCaption={onEditCaption}
        tr={tr}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 8, paddingBottom: 16 },
  hero: {
    color: CM_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 26,
    fontWeight: '700',
    marginBottom: 8,
  },
  box: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: CM_BORDER,
    borderRadius: CM_RADIUS,
    padding: 12,
    gap: 8,
  },
  boxLabel: {
    color: CM_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 15,
    fontWeight: '700',
  },
  label: {
    color: CM_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 15,
    fontWeight: '700',
    marginTop: 8,
  },
  input: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: CM_BORDER,
    borderRadius: CM_RADIUS,
    paddingHorizontal: 12,
    paddingVertical: 12,
    color: CM_TEAL_DARK,
    fontFamily: fonts.body,
    fontSize: 15,
  },
  hint: { color: CM_MUTED, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  section: {
    color: CM_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
    fontWeight: '700',
    marginTop: 12,
  },
  upload: { marginVertical: 8 },
  error: { color: '#DC2626', fontFamily: fonts.body, fontSize: 13 },
});
