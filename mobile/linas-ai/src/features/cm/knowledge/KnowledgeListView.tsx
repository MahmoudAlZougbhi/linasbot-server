import { StyleSheet, Text, View } from 'react-native';

import { LinasSparkleIcon } from '../../../components/LinasSparkleIcon';
import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { AiSetupListHeader } from '../AiSetupListHeader';
import { KnowledgeArticleCard, KnowledgeLocationsCard } from './KnowledgeCard';
import { KN_MUTED, KN_TEAL } from './knowledgeChrome';
import type { KnowledgeListRow } from './knowledgeModel';

type Props = {
  rows: KnowledgeListRow[];
  query: string;
  count: number;
  onQueryChange: (value: string) => void;
  onAdd: () => void;
  onSelect: (id: string) => void;
  onOpenLocations: () => void;
  tr: (key: StringKey) => string;
};

export function KnowledgeListView({
  rows,
  query,
  count,
  onQueryChange,
  onAdd,
  onSelect,
  onOpenLocations,
  tr,
}: Props) {
  const countLabel =
    count === 1 ? `1 ${tr('knowledgeCountOne')}` : `${count} ${tr('knowledgeCount')}`;

  return (
    <View style={styles.wrap}>
      <AiSetupListHeader
        query={query}
        onQueryChange={onQueryChange}
        searchPlaceholder={tr('knowledgeSearch')}
        addA11yLabel={tr('knowledgeAdd')}
        onAdd={onAdd}
        countLabel={countLabel}
      />

      {rows.length === 0 ? <Text style={styles.empty}>{tr('knowledgeEmpty')}</Text> : null}
      {rows.map((row) =>
        row.type === 'locations' ? (
          <KnowledgeLocationsCard key="locations" onPress={onOpenLocations} tr={tr} />
        ) : (
          <KnowledgeArticleCard
            key={row.item.id}
            item={row.item}
            untitled={tr('knowledgeUntitled')}
            onPress={() => onSelect(row.item.id)}
            tr={tr}
          />
        ),
      )}

      <View style={styles.footer}>
        <LinasSparkleIcon size={16} color={KN_TEAL} />
        <Text style={styles.footerText}>{tr('knowledgeFooter')}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 12, paddingBottom: 28, flexGrow: 1 },
  empty: { color: KN_MUTED, fontFamily: fonts.body, fontSize: 14 },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 'auto',
    paddingTop: 20,
  },
  footerText: { color: KN_MUTED, fontFamily: fonts.body, fontSize: 13, flex: 1, lineHeight: 18 },
});
