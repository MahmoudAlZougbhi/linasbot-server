import { StyleSheet, Text, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../../components/AppIcon';
import { LinasSparkleIcon } from '../../../components/LinasSparkleIcon';
import { PrimaryButton } from '../../../components/PrimaryButton';
import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { RequestRuleCard } from './RequestRuleCard';
import { RQ_BORDER, RQ_MUTED, RQ_RADIUS, RQ_TEAL, RQ_TEAL_DARK, RQ_TEAL_SOFT } from './requestRuleChrome';
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
  return (
    <View style={styles.wrap}>
      <View style={styles.hero}>
        <LinasSparkleIcon size={22} color={RQ_TEAL} />
        <Text style={styles.title}>{tr('aiSetupSec_requests_appointments')}</Text>
        <Text style={styles.subtitle}>{tr('requestRulesSubtitle')}</Text>
      </View>

      <PrimaryButton label={tr('requestRulesAdd')} onPress={onAdd} style={styles.addBtn} />

      <View style={styles.info}>
        <View style={styles.infoIcon}>
          <Text style={styles.infoI}>i</Text>
        </View>
        <View style={styles.infoCopy}>
          <Text style={styles.infoTitle}>{tr('requestRulesInfoTitle')}</Text>
          <Text style={styles.infoBody}>{tr('requestRulesInfoBody')}</Text>
        </View>
      </View>

      <View style={styles.search}>
        <AppIcon icon={feather('search')} size={18} color={RQ_MUTED} />
        <TextInput
          value={query}
          onChangeText={onQueryChange}
          placeholder={tr('requestRulesSearch')}
          placeholderTextColor={RQ_MUTED}
          style={styles.searchInput}
          autoCapitalize="none"
          autoCorrect={false}
          accessibilityLabel={tr('requestRulesSearch')}
        />
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
  hero: { alignItems: 'center', gap: 6, marginTop: 4 },
  title: {
    color: RQ_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 28,
    fontWeight: '700',
  },
  subtitle: { color: RQ_MUTED, fontFamily: fonts.body, fontSize: 15, textAlign: 'center' },
  addBtn: { backgroundColor: RQ_TEAL, borderRadius: RQ_RADIUS },
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
  search: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: RQ_BORDER,
    borderRadius: RQ_RADIUS,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  searchInput: {
    flex: 1,
    color: RQ_TEAL_DARK,
    fontFamily: fonts.body,
    fontSize: 15,
    padding: 0,
  },
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
