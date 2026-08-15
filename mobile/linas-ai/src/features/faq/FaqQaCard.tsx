import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import type { StringKey } from '../../i18n';
import { fonts } from '../../theme';
import type { FaqGroup } from './faqApi';
import { FAQ_BORDER, FAQ_ICON_SQ, FAQ_MUTED, FAQ_PAD, FAQ_RADIUS, FAQ_RADIUS_SM, FAQ_TEAL, FAQ_TEXT } from './faqChrome';
import { variantForLang, variantPreview } from './faqPreview';

type Props = {
  item: FaqGroup;
  previewLang: string;
  onEdit: (group: FaqGroup) => void;
  onDelete: (group: FaqGroup) => void;
  tr: (key: StringKey) => string;
};

export function FaqQaCard({ item, previewLang, onEdit, onDelete, tr }: Props) {
  const complete = !item.incomplete;
  const question = variantPreview(item, previewLang) || tr('faqEmptyQuestion');
  const answer = String(variantForLang(item, previewLang)?.answer || '').trim();

  return (
    <View style={styles.card}>
      <Pressable onPress={() => onEdit(item)} accessibilityRole="button">
        <Text style={styles.label}>{tr('faqQuestionLabel').toUpperCase()}</Text>
        <Text style={styles.question}>{question}</Text>
        <Text style={[styles.label, styles.answerLabel]}>{tr('faqAnswerLabel').toUpperCase()}</Text>
        <Text style={styles.answer} numberOfLines={3}>
          {answer}
        </Text>
      </Pressable>
      <View style={styles.rule} />
      <View style={styles.footer}>
        <View style={styles.statusRow}>
          {complete ? (
            <View style={styles.check}>
              <AppIcon icon={feather('check')} size={10} color="#FFFFFF" />
            </View>
          ) : null}
          <Text style={styles.status} numberOfLines={2}>
            {complete ? tr('faqTranslatedStatus') : tr('faqIncomplete')}
          </Text>
        </View>
        <View style={styles.actions}>
          <Pressable
            onPress={() => onEdit(item)}
            style={styles.iconSq}
            accessibilityRole="button"
            accessibilityLabel={tr('faqEditA11y')}
          >
            <AppIcon icon={feather('edit-2')} size={16} color={FAQ_TEAL} />
          </Pressable>
          <Pressable
            onPress={() => onDelete(item)}
            style={styles.iconSq}
            accessibilityRole="button"
            accessibilityLabel={tr('faqDeleteConfirm')}
          >
            <AppIcon icon={feather('trash-2')} size={16} color={FAQ_TEAL} />
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderColor: FAQ_BORDER,
    borderWidth: 1,
    borderRadius: FAQ_RADIUS,
    padding: FAQ_PAD,
  },
  label: {
    color: FAQ_TEAL,
    fontFamily: fonts.bodyMedium,
    fontSize: 10,
    letterSpacing: 1.1,
    fontWeight: '700',
  },
  answerLabel: { marginTop: 10 },
  question: {
    color: FAQ_TEXT,
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
    fontWeight: '700',
    marginTop: 4,
  },
  answer: {
    color: FAQ_TEXT,
    fontFamily: fonts.body,
    fontSize: 14,
    lineHeight: 20,
    marginTop: 4,
  },
  rule: {
    height: 1,
    backgroundColor: FAQ_BORDER,
    marginTop: 14,
    marginBottom: 12,
  },
  footer: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 },
  check: {
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: FAQ_TEAL,
    alignItems: 'center',
    justifyContent: 'center',
  },
  status: { color: FAQ_MUTED, fontFamily: fonts.body, fontSize: 12, flex: 1 },
  actions: { flexDirection: 'row', gap: 8 },
  iconSq: {
    width: FAQ_ICON_SQ,
    height: FAQ_ICON_SQ,
    borderRadius: FAQ_RADIUS_SM,
    borderWidth: 1,
    borderColor: FAQ_BORDER,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FFFFFF',
  },
});
