import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { ClampedLongField } from '../ClampedLongField';
import {
  KN_BORDER,
  KN_DOT,
  KN_MUTED,
  KN_RADIUS,
  KN_TEAL,
  KN_TEAL_DARK,
  KN_TEAL_PILL,
  KN_TEAL_SOFT,
} from './knowledgeChrome';
import { countWords, isPublishedStatus, type KnowledgeAttachment, type KnowledgeItem, type KnowledgeKind } from './knowledgeModel';
import { KnowledgeResourceGrid, KnowledgeResourceRows } from './KnowledgeResources';

type Props = {
  item: KnowledgeItem;
  uploading: boolean;
  uploadError: string | null;
  onTitle: (value: string) => void;
  onBody: (value: string) => void;
  onTogglePublished: () => void;
  onAddResource: (kind: KnowledgeKind) => void;
  onRemoveResource: (id: string) => void;
  onReplaceResource: (att: KnowledgeAttachment) => void;
  onEditCaption: (att: KnowledgeAttachment) => void;
  onMoveResource?: (id: string, direction: -1 | 1) => void;
  tr: (key: StringKey) => string;
};

export function KnowledgeEditView({
  item,
  uploading,
  uploadError,
  onTitle,
  onBody,
  onTogglePublished,
  onAddResource,
  onRemoveResource,
  onReplaceResource,
  onEditCaption,
  onMoveResource,
  tr,
}: Props) {
  const words = countWords(item.body);
  const published = isPublishedStatus(item.status);
  const wordLabel = words === 1 ? `1 ${tr('knowledgeWordOne')}` : `${words} ${tr('knowledgeWords')}`;

  return (
    <View style={styles.wrap}>
      <View style={styles.headingRow}>
        <Text style={styles.hero}>{tr('knowledgeEditTitle')}</Text>
        <Pressable
          onPress={onTogglePublished}
          accessibilityRole="button"
          accessibilityLabel={published ? tr('knowledgePublished') : tr('knowledgeDraft')}
          style={styles.pill}
        >
          <View style={[styles.dot, !published && styles.dotDraft]} />
          <Text style={styles.pillText}>
            {published ? tr('knowledgePublished') : tr('knowledgeDraft')}
          </Text>
        </Pressable>
      </View>

      <Text style={styles.label}>{tr('knowledgeFieldTitle')}</Text>
      <TextInput
        value={item.title}
        onChangeText={onTitle}
        style={styles.input}
        placeholder={tr('knowledgeUntitled')}
        placeholderTextColor={KN_MUTED}
      />

      <ClampedLongField
        label={tr('knowledgeFieldBody')}
        value={item.body}
        onChange={onBody}
        countLabel={wordLabel}
        labelStyle={styles.label}
        inputStyle={styles.input}
      />

      <View style={styles.info}>
        <View style={styles.infoIcon}>
          <Text style={styles.infoI}>i</Text>
        </View>
        <View style={styles.infoCopy}>
          <Text style={styles.infoTitle}>{tr('knowledgeInfoRecommended')}</Text>
          <Text style={styles.infoBody}>{tr('knowledgeInfoNotLimit')}</Text>
          <Text style={styles.infoBody}>{tr('knowledgeInfoLanguage')}</Text>
        </View>
      </View>

      <Text style={styles.section}>{tr('knowledgeResources')}</Text>
      <Text style={styles.hint}>{tr('knowledgeResourcesHint')}</Text>
      <KnowledgeResourceGrid onAdd={onAddResource} tr={tr} />
      {uploading ? <ActivityIndicator color={KN_TEAL} style={styles.upload} /> : null}
      {uploadError ? <Text style={styles.error}>{uploadError}</Text> : null}
      <KnowledgeResourceRows
        attachments={item.attachments}
        onRemove={onRemoveResource}
        onReplace={onReplaceResource}
        onEditCaption={onEditCaption}
        onMove={onMoveResource}
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
    color: KN_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 26,
    fontWeight: '700',
    flex: 1,
  },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: KN_TEAL_PILL,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: KN_DOT },
  dotDraft: { backgroundColor: '#F59E0B' },
  pillText: {
    color: KN_TEAL,
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    fontWeight: '600',
  },
  label: {
    color: KN_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 15,
    fontWeight: '700',
    marginTop: 8,
  },
  input: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: KN_BORDER,
    borderRadius: KN_RADIUS,
    paddingHorizontal: 12,
    paddingVertical: 12,
    color: KN_TEAL_DARK,
    fontFamily: fonts.body,
    fontSize: 15,
  },
  info: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    backgroundColor: KN_TEAL_SOFT,
    borderRadius: KN_RADIUS,
    padding: 12,
    marginTop: 8,
  },
  infoIcon: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: KN_TEAL,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 1,
  },
  infoI: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '700' },
  infoCopy: { flex: 1, gap: 4 },
  infoTitle: {
    color: KN_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 18,
  },
  infoBody: { color: KN_TEAL_DARK, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  section: {
    color: KN_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
    fontWeight: '700',
    marginTop: 12,
  },
  hint: { color: KN_MUTED, fontFamily: fonts.body, fontSize: 13, marginBottom: 4 },
  upload: { marginVertical: 8 },
  error: { color: '#DC2626', fontFamily: fonts.body, fontSize: 13 },
});
