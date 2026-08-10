import { Pressable, StyleSheet, Text, View } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import type { StringKey } from '../../i18n';
import { colors, fonts, radii, spacing } from '../../theme';
import { Field } from '../cm/editors/Field';
import type { FaqGroup } from './faqApi';
import { FAQ_LANGS, type FaqLangId } from './faqLanguages';
import { variantForLang } from './faqPreview';

type Props = {
  group: FaqGroup;
  activeLang: FaqLangId;
  question: string;
  answer: string;
  saving: boolean;
  onLang: (lang: FaqLangId) => void;
  onQuestion: (value: string) => void;
  onAnswer: (value: string) => void;
  onSaveVariant: () => void;
  onRegenerate: () => void;
  onArchive: () => void;
  onBack: () => void;
  tr: (key: StringKey) => string;
};

export function FaqDetailView({
  group,
  activeLang,
  question,
  answer,
  saving,
  onLang,
  onQuestion,
  onAnswer,
  onSaveVariant,
  onRegenerate,
  onArchive,
  onBack,
  tr,
}: Props) {
  return (
    <View style={styles.wrap}>
      <Text style={styles.section}>{tr('faqEditVariants')}</Text>
      <Text style={styles.sub}>
        {String(group.status || 'draft')}
        {group.incomplete ? ` · ${tr('faqIncomplete')}` : ` · ${tr('faqFourLangs')}`}
      </Text>
      <View style={styles.chips}>
        {FAQ_LANGS.map((lang) => {
          const active = activeLang === lang.id;
          const has = Boolean(variantForLang(group, lang.id));
          return (
            <Pressable
              key={lang.id}
              onPress={() => onLang(lang.id)}
              style={[styles.chip, active ? styles.chipOn : null, !has ? styles.chipMissing : null]}
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
      <PrimaryButton label={tr('faqSaveVariant')} onPress={onSaveVariant} loading={saving} />
      <PrimaryButton label={tr('faqRegenerate')} variant="ghost" onPress={onRegenerate} loading={saving} />
      <PrimaryButton label={tr('faqArchive')} variant="ghost" onPress={onArchive} loading={saving} />
      <PrimaryButton label={tr('back')} variant="ghost" onPress={onBack} />
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
  sub: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.md,
  },
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
  chipMissing: { opacity: 0.55 },
  chipText: { color: colors.text, fontFamily: fonts.body, fontSize: 12 },
  chipTextOn: { color: colors.bg },
});
