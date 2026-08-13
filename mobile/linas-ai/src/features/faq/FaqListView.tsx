import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import type { StringKey } from '../../i18n';
import { colors, fonts, radii, spacing } from '../../theme';
import type { FaqEntitlement, FaqGroup } from './faqApi';
import { langLabel } from './faqLanguages';
import { variantForLang, variantPreview } from './faqPreview';

type Props = {
  items: FaqGroup[];
  entitlement: FaqEntitlement | null;
  quotaDisplay: string | null;
  smartAnswerLanguages: string[];
  query: string;
  onQueryChange: (value: string) => void;
  onCreate: () => void;
  onAskLinas: () => void;
  onSelect: (group: FaqGroup) => void;
  onRefresh: () => void;
  onAddLanguage: () => void;
  onRemoveLanguage: (langId: string) => void;
  tr: (key: StringKey) => string;
};

export function FaqListView({
  items,
  entitlement,
  quotaDisplay,
  smartAnswerLanguages,
  query,
  onQueryChange,
  onCreate,
  onAskLinas,
  onSelect,
  onRefresh,
  onAddLanguage,
  onRemoveLanguage,
  tr,
}: Props) {
  const remaining =
    entitlement && typeof entitlement.faq_remaining_entries === 'number'
      ? entitlement.faq_remaining_entries
      : null;

  return (
    <View style={styles.wrap}>
      <View style={styles.banner}>
        <Text style={styles.bannerTitle}>{tr('faqWhyTitle')}</Text>
        <Text style={styles.bannerBody}>{tr('faqWhyBody')}</Text>
        {quotaDisplay ? (
          <Text style={styles.quota}>
            {tr('faqQuota')}: {quotaDisplay}
            {remaining != null ? ` · ${remaining} ${tr('faqRemaining')}` : ''}
          </Text>
        ) : null}
        {entitlement?.upgrade_message ? <Text style={styles.warn}>{entitlement.upgrade_message}</Text> : null}
      </View>

      <PrimaryButton label={tr('faqCreateNew')} onPress={onCreate} />
      <PrimaryButton label={tr('faqAskLinas')} variant="ghost" onPress={onAskLinas} />

      <View style={styles.langHeader}>
        <Text style={styles.section}>{tr('faqLangSection')}</Text>
        <Pressable onPress={onAddLanguage} style={styles.addLangBtn}>
          <Text style={styles.addLangText}>+ {tr('faqAddLanguage')}</Text>
        </Pressable>
      </View>
      <Text style={styles.hint}>{tr('faqLangHint')}</Text>
      <View style={styles.chips}>
        {smartAnswerLanguages.map((langId) => (
          <Pressable key={langId} style={styles.chip} onLongPress={() => onRemoveLanguage(langId)}>
            <Text style={styles.chipText}>{langLabel(langId)}</Text>
            <Text style={styles.chipX}>×</Text>
          </Pressable>
        ))}
      </View>

      <View style={styles.listHeader}>
        <Text style={styles.count}>
          {items.length} {tr('faqAnswersCount')}
        </Text>
        <TextInput
          value={query}
          onChangeText={onQueryChange}
          placeholder={tr('faqSearchPlaceholder')}
          placeholderTextColor={colors.textMuted}
          style={styles.search}
        />
      </View>

      {items.length === 0 ? <Text style={styles.hint}>{tr('faqEmpty')}</Text> : null}
      {items.map((item) => {
        const preview = variantPreview(item);
        const complete = !item.incomplete;
        return (
          <Pressable key={String(item.qa_group_id)} style={styles.card} onPress={() => onSelect(item)}>
            <Text style={styles.qLabel}>{tr('likeFaqQuestion').toUpperCase()}</Text>
            <Text style={styles.question}>{preview || tr('faqEmptyQuestion')}</Text>
            <Text style={styles.aLabel}>{tr('likeFaqAnswer').toUpperCase()}</Text>
            <Text style={styles.answer} numberOfLines={2}>
              {variantForLang(item, smartAnswerLanguages[0] || 'en')?.answer || ''}
            </Text>
            <Text style={styles.status}>
              {complete ? tr('faqTranslatedStatus') : tr('faqIncomplete')}
            </Text>
          </Pressable>
        );
      })}
      <PrimaryButton label={tr('retry')} variant="ghost" onPress={onRefresh} />
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
  section: {
    color: colors.textDim,
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  langHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  addLangBtn: {
    borderWidth: 1,
    borderColor: colors.accent,
    borderRadius: radii.pill,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  addLangText: { color: colors.accent, fontFamily: fonts.bodyMedium, fontSize: 12 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.accent,
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: colors.surface,
  },
  chipText: { color: colors.accent, fontFamily: fonts.body, fontSize: 12 },
  chipX: { color: colors.accent, fontSize: 14 },
  listHeader: { gap: spacing.sm },
  count: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    gap: 4,
  },
  qLabel: { color: colors.accent, fontFamily: fonts.bodyMedium, fontSize: 10, letterSpacing: 0.6 },
  aLabel: { color: colors.accent, fontFamily: fonts.bodyMedium, fontSize: 10, letterSpacing: 0.6, marginTop: 6 },
  question: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 15 },
  answer: { color: colors.textDim, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  status: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12, marginTop: 8 },
  hint: { color: colors.textDim, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  quota: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 13, marginTop: 4 },
  warn: { color: colors.danger, fontFamily: fonts.body, fontSize: 12, marginTop: 4 },
  search: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    color: colors.text,
    fontFamily: fonts.body,
    fontSize: 14,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
  },
});
