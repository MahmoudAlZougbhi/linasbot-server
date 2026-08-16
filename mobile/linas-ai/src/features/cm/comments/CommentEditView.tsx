import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import {
  CM_BORDER,
  CM_DOT,
  CM_MUTED,
  CM_RADIUS,
  CM_TEAL,
  CM_TEAL_DARK,
  CM_TEAL_PILL,
} from './commentChrome';
import {
  postsModeOf,
  replyInOf,
  replyTypeOf,
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
  onToggleActive: () => void;
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
  onToggleActive,
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
      <View style={styles.headingRow}>
        <Text style={styles.hero}>{tr(isAi ? 'commentsEditAi' : 'commentsEditAutomatic')}</Text>
        <Pressable
          onPress={onToggleActive}
          accessibilityRole="button"
          accessibilityLabel={item.enabled ? tr('commentsActive') : tr('commentsInactive')}
          style={styles.pill}
        >
          <View style={[styles.dot, !item.enabled && styles.dotOff]} />
          <Text style={styles.pillText}>{item.enabled ? tr('commentsActive') : tr('commentsInactive')}</Text>
        </Pressable>
      </View>

      <Text style={styles.label}>{tr('commentsFieldTitle')}</Text>
      <TextInput
        value={item.name}
        onChangeText={onTitle}
        style={styles.input}
        placeholder={tr('commentsUntitled')}
        placeholderTextColor={CM_MUTED}
      />

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

      {isAi ? (
        <>
          <Text style={styles.label}>{tr('commentsNote')}</Text>
          <TextInput
            value={item.ai_instructions}
            onChangeText={onNote}
            style={[styles.input, styles.area]}
            multiline
            textAlignVertical="top"
            placeholder={tr('commentsNote')}
            placeholderTextColor={CM_MUTED}
          />
          <Text style={styles.hint}>{tr('commentsNoteHint')}</Text>
        </>
      ) : (
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
          <Text style={styles.label}>{tr('commentsReplyMessage')}</Text>
          <TextInput
            value={item.reply_template}
            onChangeText={onReplyMessage}
            style={[styles.input, styles.areaShort]}
            multiline
            textAlignVertical="top"
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
  headingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    marginBottom: 8,
  },
  hero: {
    color: CM_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 26,
    fontWeight: '700',
    flex: 1,
  },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: CM_TEAL_PILL,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: CM_DOT },
  dotOff: { backgroundColor: '#F59E0B' },
  pillText: { color: CM_TEAL, fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '600' },
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
  area: { minHeight: 120 },
  areaShort: { minHeight: 72 },
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
