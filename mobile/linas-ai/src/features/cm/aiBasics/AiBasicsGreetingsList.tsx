import { StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../../components/AppIcon';
import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { AiSetupDeletableRow } from '../AiSetupDeletableRow';
import { AiSetupListHeader } from '../AiSetupListHeader';
import { AB_MUTED, AB_TEAL } from './aiBasicsChrome';
import { matchesGreetingQuery, type GreetingRule } from './aiBasicsModel';
import { GreetingCard } from './GreetingCard';

type Props = {
  items: GreetingRule[];
  query: string;
  onQueryChange: (value: string) => void;
  onAdd: () => void;
  onSelect: (id: string) => void;
  onRequestDelete: (id: string) => void;
  tr: (key: StringKey) => string;
};

export function AiBasicsGreetingsList({
  items,
  query,
  onQueryChange,
  onAdd,
  onSelect,
  onRequestDelete,
  tr,
}: Props) {
  const rows = items.filter((item) => matchesGreetingQuery(item, query));

  return (
    <View style={styles.wrap}>
      <AiSetupListHeader
        query={query}
        onQueryChange={onQueryChange}
        searchPlaceholder={tr('aiSetupGreetingsSearch')}
        addA11yLabel={tr('aiSetupAddGreeting')}
        onAdd={onAdd}
      />

      {rows.length === 0 ? <Text style={styles.empty}>{tr('aiSetupGreetingsEmpty')}</Text> : null}
      {rows.map((item) => (
        <AiSetupDeletableRow
          key={item.id}
          deleteLabel={tr('aiSetupDeleteGreeting')}
          onRequestDelete={() => onRequestDelete(item.id)}
        >
          <GreetingCard
            item={item}
            untitled={tr('aiSetupGreetingUntitled')}
            activeLabel={tr('aiSetupGreetingActive')}
            onPress={() => onSelect(item.id)}
            onLongPress={() => onRequestDelete(item.id)}
          />
        </AiSetupDeletableRow>
      ))}

      <View style={styles.footer}>
        <AppIcon icon={feather('info')} size={16} color={AB_TEAL} />
        <Text style={styles.footerText}>{tr('aiSetupGreetingsFooter')}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 12, paddingBottom: 28, flexGrow: 1 },
  empty: { color: AB_MUTED, fontFamily: fonts.body, fontSize: 14 },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 'auto',
    paddingTop: 20,
  },
  footerText: { color: AB_MUTED, fontFamily: fonts.body, fontSize: 13, flex: 1, lineHeight: 18 },
});
