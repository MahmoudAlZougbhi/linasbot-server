import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../../components/AppIcon';
import { LinasSparkleIcon } from '../../../components/LinasSparkleIcon';
import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { KnowledgeArticleCard, KnowledgeLocationsCard } from './KnowledgeCard';
import { KN_BORDER, KN_MUTED, KN_RADIUS, KN_TEAL, KN_TEAL_DARK } from './knowledgeChrome';
import type { KnowledgeListRow } from './knowledgeModel';

type Props = {
  rows: KnowledgeListRow[];
  query: string;
  count: number;
  onQueryChange: (value: string) => void;
  onSelect: (id: string) => void;
  onOpenLocations: () => void;
  tr: (key: StringKey) => string;
};

export function KnowledgeListView({
  rows,
  query,
  count,
  onQueryChange,
  onSelect,
  onOpenLocations,
  tr,
}: Props) {
  const countLabel =
    count === 1 ? `1 ${tr('knowledgeCountOne')}` : `${count} ${tr('knowledgeCount')}`;

  return (
    <View style={styles.wrap}>
      <Text style={styles.hero}>{tr('aiSetupSec_knowledge')}</Text>
      <Text style={styles.subtitle}>{tr('knowledgeSubtitle')}</Text>

      <View style={styles.search}>
        <AppIcon icon={feather('search')} size={18} color={KN_MUTED} />
        <TextInput
          value={query}
          onChangeText={onQueryChange}
          placeholder={tr('knowledgeSearch')}
          placeholderTextColor={KN_MUTED}
          style={styles.searchInput}
          autoCapitalize="none"
          autoCorrect={false}
          accessibilityLabel={tr('knowledgeSearch')}
        />
      </View>

      <Text style={styles.count}>{countLabel}</Text>

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
  hero: {
    color: KN_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 28,
    fontWeight: '700',
    marginTop: 4,
  },
  subtitle: { color: KN_MUTED, fontFamily: fonts.body, fontSize: 15, marginTop: -4 },
  search: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: KN_BORDER,
    borderRadius: KN_RADIUS,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  searchInput: {
    flex: 1,
    color: KN_TEAL_DARK,
    fontFamily: fonts.body,
    fontSize: 15,
    padding: 0,
  },
  count: { color: KN_MUTED, fontFamily: fonts.body, fontSize: 13, marginTop: 4 },
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
