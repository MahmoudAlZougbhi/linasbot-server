import { Pressable, StyleSheet, Text, View } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import type { StringKey } from '../../i18n';
import { colors, fonts, radii, spacing } from '../../theme';
import { Field } from '../cm/editors/Field';
import { FAQ_LANGS, type FaqLangId } from './faqLanguages';

type Props = {
  question: string;
  answer: string;
  language: FaqLangId;
  saving: boolean;
  onQuestion: (value: string) => void;
  onAnswer: (value: string) => void;
  onLanguage: (value: FaqLangId) => void;
  onSave: () => void;
  onCancel: () => void;
  tr: (key: StringKey) => string;
};

export function FaqCreateView({
  question,
  answer,
  language,
  saving,
  onQuestion,
  onAnswer,
  onLanguage,
  onSave,
  onCancel,
  tr,
}: Props) {
  return (
    <View style={styles.wrap}>
      <Text style={styles.hint}>{tr('faqCreateHint')}</Text>
      <Text style={styles.section}>{tr('faqSourceLanguage')}</Text>
      <View style={styles.chips}>
        {FAQ_LANGS.map((lang) => {
          const active = language === lang.id;
          return (
            <Pressable
              key={lang.id}
              onPress={() => onLanguage(lang.id)}
              style={[styles.chip, active ? styles.chipOn : null]}
            >
              <Text style={[styles.chipText, active ? styles.chipTextOn : null]}>{tr(lang.labelKey)}</Text>
            </Pressable>
          );
        })}
      </View>
      <View style={styles.card}>
        <Field label={tr('likeFaqQuestion')} value={question} onChange={onQuestion} multiline />
        <Field label={tr('likeFaqAnswer')} value={answer} onChange={onAnswer} multiline />
      </View>
      <View style={styles.actions}>
        <PrimaryButton label={tr('likeFaqSave')} onPress={onSave} loading={saving} style={{ flex: 1 }} />
        <PrimaryButton label={tr('usersCancel')} variant="ghost" onPress={onCancel} style={{ flex: 1 }} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.md, paddingBottom: 40 },
  section: {
    color: colors.textDim,
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.md,
  },
  hint: { color: colors.textDim, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: colors.surface,
  },
  chipOn: { backgroundColor: colors.text, borderColor: colors.text },
  chipText: { color: colors.text, fontFamily: fonts.body, fontSize: 12 },
  chipTextOn: { color: colors.bg },
  actions: { flexDirection: 'row', gap: 8 },
});
