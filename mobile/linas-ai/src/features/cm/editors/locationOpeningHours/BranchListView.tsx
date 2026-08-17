import { ScrollView, Text, View } from 'react-native';

import { LinasSparkleIcon } from '../../../../components/LinasSparkleIcon';
import { useI18n } from '../../../../i18n/LanguageContext';
import { AiSetupListHeader } from '../../AiSetupListHeader';
import { locStyles, locTeal } from './locationHoursStyles';
import { BranchCard } from './BranchCard';
import { matchesBranchQuery } from './branchScheduleHelpers';

type Props = {
  items: Record<string, unknown>[];
  query: string;
  onQuery: (value: string) => void;
  onAdd: () => void;
  onOpen: (id: string) => void;
};

export function BranchListView({ items, query, onQuery, onAdd, onOpen }: Props) {
  const { tr } = useI18n();
  const visible = items.filter((item) => matchesBranchQuery(item, query));
  const countLabel =
    visible.length === 1
      ? `1 ${tr('aiSetupLocCountOne')}`
      : `${visible.length} ${tr('aiSetupLocCount')}`;

  return (
    <ScrollView
      contentContainerStyle={{ paddingBottom: 48 }}
      keyboardShouldPersistTaps="handled"
      showsVerticalScrollIndicator={false}
      showsHorizontalScrollIndicator={false}
    >
      <AiSetupListHeader
        query={query}
        onQueryChange={onQuery}
        searchPlaceholder={tr('aiSetupLocSearch')}
        addA11yLabel={tr('aiSetupLocAddBranch')}
        onAdd={onAdd}
        countLabel={countLabel}
      />
      {visible.length === 0 ? <Text style={locStyles.sectionHint}>{tr('aiSetupLocEmpty')}</Text> : null}
      {visible.map((item) => (
        <BranchCard key={String(item.id)} branch={item} onPress={() => onOpen(String(item.id))} />
      ))}
      <View style={locStyles.infoBanner}>
        <LinasSparkleIcon size={16} color={locTeal} />
        <Text style={locStyles.infoText}>{tr('aiSetupLocBanner')}</Text>
      </View>
    </ScrollView>
  );
}
