import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import type { StringKey } from '../../i18n';
import { colors, fonts, radii, spacing } from '../../theme';
import type { FaqEntitlement, FaqGroup } from './faqApi';
import { variantPreview } from './faqPreview';

type Props = {
  items: FaqGroup[];
  entitlement: FaqEntitlement | null;
  quotaDisplay: string | null;
  query: string;
  onQueryChange: (value: string) => void;
  onCreate: () => void;
  onAskLinas: () => void;
  onSelect: (group: FaqGroup) => void;
  onRefresh: () => void;
  tr: (key: StringKey) => string;
};

export function FaqListView({
  items,
  entitlement,
  quotaDisplay,
  query,
  onQueryChange,
  onCreate,
  onAskLinas,
  onSelect,
  onRefresh,
  tr,
}: Props) {
  const remaining =
    entitlement && typeof entitlement.faq_remaining_entries === 'number'
      ? entitlement.faq_remaining_entries
      : null;

  return (
    <View style={styles.wrap}>
      <View style={styles.card}>
        <Text style={styles.section}>{tr('faqWhyTitle')}</Text>
        <Text style={styles.hint}>{tr('faqWhyBody')}</Text>
        {quotaDisplay ? (
          <Text style={styles.quota}>
            {tr('faqQuota')}: {quotaDisplay}
            {remaining != null ? ` · ${remaining} ${tr('faqRemaining')}` : ''}
          </Text>
        ) : null}
        {entitlement?.upgrade_message ? <Text style={styles.warn}>{entitlement.upgrade_message}</Text> : null}
      </View>

      <PrimaryButton label={tr('faqAskLinas')} onPress={onAskLinas} />
      <PrimaryButton label={tr('faqCreateNew')} onPress={onCreate} />

      <TextInput
        value={query}
        onChangeText={onQueryChange}
        placeholder={tr('faqSearchPlaceholder')}
        placeholderTextColor={colors.textMuted}
        style={styles.search}
      />

      <Text style={styles.section}>{tr('faqSavedList')}</Text>
      {items.length === 0 ? <Text style={styles.hint}>{tr('faqEmpty')}</Text> : null}
      {items.map((item) => (
        <Pressable key={String(item.qa_group_id)} style={styles.card} onPress={() => onSelect(item)}>
          <Text style={styles.title}>{variantPreview(item)}</Text>
          <Text style={styles.sub}>
            {String(item.status || 'draft')}
            {item.incomplete ? ` · ${tr('faqIncomplete')}` : ` · ${tr('faqFourLangs')}`}
          </Text>
        </Pressable>
      ))}
      <PrimaryButton label={tr('retry')} variant="ghost" onPress={onRefresh} />
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
    gap: 6,
  },
  title: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 15 },
  sub: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12 },
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
