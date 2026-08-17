import { StyleSheet, Text, View } from 'react-native';

import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { AiSetupListHeader } from '../AiSetupListHeader';
import { RequestRuleCard } from './RequestRuleCard';
import { RQ_MUTED, RQ_RADIUS, RQ_TEAL, RQ_TEAL_DARK, RQ_TEAL_SOFT } from './requestRuleChrome';
import type { RequestGraphRow, RequestRuleItem } from './requestRuleModel';

type Props = {
  items: RequestRuleItem[];
  graphsBySource: Record<string, RequestGraphRow>;
  query: string;
  onQueryChange: (value: string) => void;
  onAdd: () => void;
  onSelect: (id: string) => void;
  tr: (key: StringKey) => string;
};

export function RequestRuleListView({
  items,
  graphsBySource,
  query,
  onQueryChange,
  onAdd,
  onSelect,
  tr,
}: Props) {
  const countLabel =
    items.length === 1
      ? `1 ${tr('requestRulesCountOne')}`
      : `${items.length} ${tr('requestRulesCount')}`;

  return (
    <View style={styles.wrap}>
      <AiSetupListHeader
        title={tr('aiSetupSec_requests_appointments')}
        subtitle={tr('requestRulesSubtitle')}
        query={query}
        onQueryChange={onQueryChange}
        searchPlaceholder={tr('requestRulesSearch')}
        addA11yLabel={tr('requestRulesAdd')}
        onAdd={onAdd}
        countLabel={countLabel}
      />

      <View style={styles.info}>
        <View style={styles.infoIcon}>
          <Text style={styles.infoI}>i</Text>
        </View>
        <View style={styles.infoCopy}>
          <Text style={styles.infoTitle}>{tr('requestRulesInfoTitle')}</Text>
          <Text style={styles.infoBody}>{tr('requestRulesInfoBody')}</Text>
        </View>
      </View>

      {items.length === 0 ? <Text style={styles.empty}>{tr('requestRulesEmpty')}</Text> : null}
      {items.map((item) => (
        <RequestRuleCard
          key={item.id}
          item={item}
          graph={graphsBySource[item.id]}
          untitled={tr('requestRulesUntitled')}
          onPress={() => onSelect(item.id)}
          tr={tr}
        />
      ))}

      <Text style={styles.footer}>{tr('requestRulesFooter')}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 12, paddingBottom: 28, flexGrow: 1 },
  info: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    backgroundColor: RQ_TEAL_SOFT,
    borderRadius: RQ_RADIUS,
    padding: 12,
  },
  infoIcon: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: RQ_TEAL,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 1,
  },
  infoI: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '700' },
  infoCopy: { flex: 1, gap: 4 },
  infoTitle: {
    color: RQ_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    fontWeight: '700',
  },
  infoBody: { color: RQ_TEAL_DARK, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  empty: { color: RQ_MUTED, fontFamily: fonts.body, fontSize: 14 },
  footer: {
    color: RQ_MUTED,
    fontFamily: fonts.body,
    fontSize: 13,
    textAlign: 'center',
    marginTop: 'auto',
    paddingTop: 16,
    lineHeight: 18,
  },
});
