import { ActivityIndicator, StyleSheet, Text, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../../components/AppIcon';
import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { ClampedLongField } from '../ClampedLongField';
import { KnowledgeResourceGrid, KnowledgeResourceRows } from '../knowledge/KnowledgeResources';
import { countWords, type KnowledgeAttachment, type KnowledgeKind } from '../knowledge/knowledgeModel';
import {
  AB_BORDER,
  AB_FOREST,
  AB_MUTED,
  AB_RADIUS,
  AB_TEAL,
  AB_TEAL_SOFT,
  AB_TEXT,
} from './aiBasicsChrome';
import type { GreetingRule } from './aiBasicsModel';

type Props = {
  item: GreetingRule;
  isNew: boolean;
  uploading: boolean;
  uploadError: string | null;
  onTitle: (value: string) => void;
  onNote: (value: string) => void;
  onAddResource: (kind: KnowledgeKind) => void;
  onRemoveResource: (id: string) => void;
  onReplaceResource: (att: KnowledgeAttachment) => void;
  onEditCaption: (att: KnowledgeAttachment) => void;
  onMoveResource?: (id: string, direction: -1 | 1) => void;
  tr: (key: StringKey) => string;
};

export function GreetingEditView({
  item,
  isNew,
  uploading,
  uploadError,
  onTitle,
  onNote,
  onAddResource,
  onRemoveResource,
  onReplaceResource,
  onEditCaption,
  onMoveResource,
  tr,
}: Props) {
  const words = countWords(item.notes);
  const wordLabel = words === 1 ? `1 ${tr('knowledgeWordOne')}` : `${words} ${tr('knowledgeWords')}`;

  return (
    <View style={styles.wrap}>
      <View style={styles.hero}>
        <View style={styles.heroIcon}>
          <AppIcon icon={feather('message-circle')} size={22} color={AB_FOREST} />
        </View>
        <Text style={styles.heroTitle}>
          {isNew ? tr('aiSetupAddGreeting') : tr('aiSetupGreetingEditTitle')}
        </Text>
      </View>

      <Text style={styles.label}>{tr('aiSetupGreetingTitle')}</Text>
      <TextInput
        value={item.name}
        onChangeText={onTitle}
        placeholder={tr('aiSetupGreetingTitlePlaceholder')}
        placeholderTextColor={AB_MUTED}
        style={styles.input}
      />

      <Text style={styles.label}>{tr('aiSetupGreetingNote')}</Text>
      <Text style={styles.helper}>{tr('aiSetupGreetingNoteHelper')}</Text>
      <ClampedLongField
        value={item.notes}
        onChange={onNote}
        countLabel={wordLabel}
        inputStyle={styles.area}
        placeholderTextColor={AB_MUTED}
      />

      <Text style={[styles.label, styles.sectionGap]}>{tr('aiSetupGreetingResources')}</Text>
      <Text style={styles.helper}>{tr('aiSetupGreetingResourcesHint')}</Text>
      <KnowledgeResourceGrid onAdd={onAddResource} tr={tr} />
      {uploading ? <ActivityIndicator color={AB_TEAL} style={styles.upload} /> : null}
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
  wrap: { gap: 6, paddingBottom: 16 },
  hero: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 12 },
  heroIcon: {
    width: 44,
    height: 44,
    borderRadius: 10,
    backgroundColor: AB_TEAL_SOFT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  heroTitle: {
    color: AB_FOREST,
    fontFamily: fonts.bodyMedium,
    fontSize: 22,
    fontWeight: '700',
    flex: 1,
  },
  label: {
    color: AB_FOREST,
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 4,
    marginTop: 8,
  },
  helper: { color: AB_MUTED, fontFamily: fonts.body, fontSize: 13, lineHeight: 18, marginBottom: 6 },
  sectionGap: { marginTop: 14 },
  input: {
    borderWidth: 1,
    borderColor: AB_BORDER,
    borderRadius: AB_RADIUS,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: AB_TEXT,
    fontFamily: fonts.body,
    fontSize: 15,
  },
  area: {
    borderWidth: 1,
    borderColor: AB_BORDER,
    borderRadius: AB_RADIUS,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: AB_TEXT,
    fontFamily: fonts.body,
    fontSize: 15,
    minHeight: 120,
  },
  upload: { marginVertical: 8 },
  error: { color: '#DC2626', fontFamily: fonts.body, fontSize: 13 },
});
