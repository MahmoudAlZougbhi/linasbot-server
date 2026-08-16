import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { CommentSegmented } from '../comments/CommentSegmented';
import { RQ_BORDER, RQ_DOT, RQ_MUTED, RQ_RADIUS, RQ_TEAL, RQ_TEAL_DARK, RQ_TEAL_PILL } from './requestRuleChrome';
import {
  collectsPhrase,
  isGraphPublished,
  type RequestGraphRow,
  type RequestRuleItem,
  type RequestRuleType,
} from './requestRuleModel';

type Props = {
  item: RequestRuleItem;
  graph?: RequestGraphRow;
  preview?: RequestGraphRow;
  onTitle: (value: string) => void;
  onType: (value: RequestRuleType) => void;
  onNote: (value: string) => void;
  onPreview: () => void;
  tr: (key: StringKey) => string;
};

export function RequestRuleEditView({
  item,
  graph,
  preview,
  onTitle,
  onType,
  onNote,
  onPreview,
  tr,
}: Props) {
  const published = isGraphPublished(graph);
  const fields = preview || graph;
  const collects = collectsPhrase(fields, tr('requestRulesCollectsEmpty'));

  return (
    <View style={styles.wrap}>
      <View style={styles.headingRow}>
        <Text style={styles.hero}>{tr('requestRulesEditTitle')}</Text>
        <View style={styles.pill}>
          <View style={[styles.dot, !published && styles.dotOff]} />
          <Text style={styles.pillText}>
            {published ? tr('requestRulesPublished') : tr('requestRulesDraft')}
          </Text>
        </View>
      </View>

      <CommentSegmented
        label={tr('aiSetupRequestType')}
        value={item.type}
        options={[
          { id: 'APPOINTMENT', label: tr('aiSetupRequestTypeAppointment') },
          { id: 'ORDER', label: tr('aiSetupRequestTypeOrder') },
          { id: 'OTHER', label: tr('aiSetupRequestTypeOther') },
        ]}
        onChange={onType}
      />

      <Text style={styles.label}>{tr('aiSetupRequestTitle')}</Text>
      <TextInput
        value={item.name}
        onChangeText={onTitle}
        style={styles.input}
        placeholder={tr('requestRulesUntitled')}
        placeholderTextColor={RQ_MUTED}
      />

      <Text style={styles.label}>{tr('requestRulesNote')}</Text>
      <TextInput
        value={item.notes}
        onChangeText={onNote}
        style={[styles.input, styles.area]}
        multiline
        textAlignVertical="top"
        placeholder={tr('requestRulesNote')}
        placeholderTextColor={RQ_MUTED}
      />
      <Text style={styles.hint}>{tr('requestRulesNoteHint')}</Text>

      <Pressable onPress={onPreview} accessibilityRole="button" style={styles.previewBtn}>
        <Text style={styles.previewText}>{tr('aiSetupRequestPreview')}</Text>
      </Pressable>
      <Text style={styles.collects}>
        {collects === tr('requestRulesCollectsEmpty')
          ? collects
          : tr('requestRulesCollects').replace('{fields}', collects)}
      </Text>
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
    color: RQ_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 26,
    fontWeight: '700',
    flex: 1,
  },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: RQ_TEAL_PILL,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: RQ_DOT },
  dotOff: { backgroundColor: '#F59E0B' },
  pillText: { color: RQ_TEAL, fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '600' },
  label: {
    color: RQ_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 15,
    fontWeight: '700',
    marginTop: 8,
  },
  input: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: RQ_BORDER,
    borderRadius: RQ_RADIUS,
    paddingHorizontal: 12,
    paddingVertical: 12,
    color: RQ_TEAL_DARK,
    fontFamily: fonts.body,
    fontSize: 15,
  },
  area: { minHeight: 120 },
  hint: { color: RQ_MUTED, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  previewBtn: {
    borderWidth: 1.5,
    borderColor: RQ_TEAL,
    borderRadius: RQ_RADIUS,
    paddingVertical: 12,
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    marginTop: 8,
  },
  previewText: { color: RQ_TEAL, fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
  collects: { color: RQ_MUTED, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
});
