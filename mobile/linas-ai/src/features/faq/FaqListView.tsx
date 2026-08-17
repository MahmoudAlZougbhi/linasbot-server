import { useEffect, useMemo, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { StringKey } from '../../i18n';
import { fonts, spacing } from '../../theme';
import { AiSetupListHeader } from '../cm/AiSetupListHeader';
import type { FaqEntitlement, FaqGroup } from './faqApi';
import { FaqInfoBanner } from './FaqInfoBanner';
import { FaqLanguagesCard } from './FaqLanguagesCard';
import { FaqQaCard } from './FaqQaCard';
import { sortLangIds } from './faqLanguages';

type Props = {
  items: FaqGroup[];
  entitlement: FaqEntitlement | null;
  smartAnswerLanguages: string[];
  query: string;
  onQueryChange: (value: string) => void;
  onCreate: () => void;
  onSelect: (group: FaqGroup) => void;
  onDelete: (group: FaqGroup) => void;
  onAddLanguage: () => void;
  onRemoveLanguage: (langId: string) => void;
  tr: (key: StringKey) => string;
};

export function FaqListView({
  items,
  entitlement,
  smartAnswerLanguages,
  query,
  onQueryChange,
  onCreate,
  onSelect,
  onDelete,
  onAddLanguage,
  onRemoveLanguage,
  tr,
}: Props) {
  const languages = useMemo(() => sortLangIds(smartAnswerLanguages), [smartAnswerLanguages]);
  const [previewLang, setPreviewLang] = useState('en');

  useEffect(() => {
    if (languages.includes(previewLang)) return;
    const next = languages.includes('en') ? 'en' : languages[0];
    if (next) setPreviewLang(next);
  }, [languages, previewLang]);

  return (
    <View style={styles.wrap}>
      <AiSetupListHeader
        title={tr('faqTitle')}
        subtitle={tr('faqSub')}
        query={query}
        onQueryChange={onQueryChange}
        searchPlaceholder={tr('faqSearchPlaceholder')}
        addA11yLabel={tr('faqCreateNew')}
        onAdd={onCreate}
        countLabel={`${items.length} ${tr('faqAnswersCount')}`}
      />

      <FaqInfoBanner upgradeMessage={entitlement?.upgrade_message} tr={tr} />

      <FaqLanguagesCard
        languages={languages}
        previewLang={languages.includes(previewLang) ? previewLang : languages[0] || 'en'}
        onPreviewLang={setPreviewLang}
        onAddLanguage={onAddLanguage}
        onRemoveLanguage={onRemoveLanguage}
        tr={tr}
      />

      {items.length === 0 ? <Text style={styles.empty}>{tr('faqEmpty')}</Text> : null}
      {items.map((item) => (
        <FaqQaCard
          key={String(item.qa_group_id)}
          item={item}
          previewLang={previewLang}
          onEdit={onSelect}
          onDelete={onDelete}
          tr={tr}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.md, paddingBottom: 40 },
  empty: { color: '#94A3B8', fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
});
