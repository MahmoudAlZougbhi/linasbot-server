import { ScrollView, Text, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../../../components/AppIcon';
import { useI18n } from '../../../../i18n/LanguageContext';
import { locStyles, locTeal } from './locationHoursStyles';
import { BranchCard } from './BranchCard';
import { matchesBranchQuery } from './branchScheduleHelpers';

type Props = {
  items: Record<string, unknown>[];
  query: string;
  onQuery: (value: string) => void;
  onOpen: (id: string) => void;
};

export function BranchListView({ items, query, onQuery, onOpen }: Props) {
  const { tr } = useI18n();
  const visible = items.filter((item) => matchesBranchQuery(item, query));

  return (
    <ScrollView contentContainerStyle={{ paddingBottom: 48 }} keyboardShouldPersistTaps="handled">
      <View style={locStyles.searchWrap}>
        <AppIcon icon={feather('search')} size={16} color="#8A9A98" />
        <TextInput
          style={locStyles.searchInput}
          value={query}
          onChangeText={onQuery}
          placeholder={tr('aiSetupLocSearch')}
          placeholderTextColor="#8A9A98"
          autoCorrect={false}
        />
      </View>
      {visible.length === 0 ? <Text style={locStyles.sectionHint}>{tr('aiSetupLocEmpty')}</Text> : null}
      {visible.map((item) => (
        <BranchCard key={String(item.id)} branch={item} onPress={() => onOpen(String(item.id))} />
      ))}
      <View style={locStyles.infoBanner}>
        <AppIcon icon={feather('star')} size={16} color={locTeal} />
        <Text style={locStyles.infoText}>{tr('aiSetupLocBanner')}</Text>
      </View>
    </ScrollView>
  );
}
