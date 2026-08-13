import { StyleSheet, Text, View } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import type { StringKey } from '../../i18n';
import { colors, fonts, radii, spacing } from '../../theme';
import { Field } from '../cm/editors/Field';

type Props = {
  question: string;
  answer: string;
  saving: boolean;
  onQuestion: (value: string) => void;
  onAnswer: (value: string) => void;
  onSave: () => void;
  onCancel: () => void;
  tr: (key: StringKey) => string;
};

export function FaqCreateView({
  question,
  answer,
  saving,
  onQuestion,
  onAnswer,
  onSave,
  onCancel,
  tr,
}: Props) {
  return (
    <View style={styles.wrap}>
      <View style={styles.banner}>
        <Text style={styles.bannerTitle}>{tr('faqCreateBannerTitle')}</Text>
        <Text style={styles.bannerBody}>{tr('faqCreateBannerBody')}</Text>
      </View>
      <View style={styles.card}>
        <Field label={tr('likeFaqQuestion')} value={question} onChange={onQuestion} multiline />
        <Field label={tr('likeFaqAnswer')} value={answer} onChange={onAnswer} multiline />
      </View>
      <PrimaryButton label={tr('faqSaveTranslate')} onPress={onSave} loading={saving} />
      <Text style={styles.footer}>{tr('faqCreateFooter')}</Text>
      <PrimaryButton label={tr('usersCancel')} variant="ghost" onPress={onCancel} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.md, paddingBottom: 40 },
  banner: {
    backgroundColor: '#E8F7F7',
    borderRadius: radii.lg,
    padding: spacing.lg,
    gap: 6,
  },
  bannerTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 15 },
  bannerBody: { color: colors.textDim, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.md,
  },
  footer: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12, textAlign: 'center' },
});
