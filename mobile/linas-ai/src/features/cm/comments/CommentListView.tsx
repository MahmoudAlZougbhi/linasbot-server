import { StyleSheet, Text, View } from 'react-native';

import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { AiSetupListHeader } from '../AiSetupListHeader';
import { CommentCard } from './CommentCard';
import { CM_MUTED, CM_RADIUS, CM_TEAL, CM_TEAL_DARK, CM_TEAL_SOFT } from './commentChrome';
import type { CommentRuleItem } from './commentModel';

type Props = {
  items: CommentRuleItem[];
  query: string;
  onQueryChange: (value: string) => void;
  onAdd: () => void;
  onSelect: (id: string) => void;
  tr: (key: StringKey) => string;
};

export function CommentListView({ items, query, onQueryChange, onAdd, onSelect, tr }: Props) {
  const countLabel =
    items.length === 1 ? `1 ${tr('commentsCountOne')}` : `${items.length} ${tr('commentsCount')}`;

  return (
    <View style={styles.wrap}>
      <AiSetupListHeader
        title={tr('aiSetupSec_comments')}
        subtitle={tr('commentsSubtitle')}
        query={query}
        onQueryChange={onQueryChange}
        searchPlaceholder={tr('commentsSearch')}
        addA11yLabel={tr('commentsAdd')}
        onAdd={onAdd}
        countLabel={countLabel}
      />

      <View style={styles.info}>
        <View style={styles.infoIcon}>
          <Text style={styles.infoI}>i</Text>
        </View>
        <View style={styles.infoCopy}>
          <Text style={styles.infoTitle}>{tr('commentsInfoTitle')}</Text>
          <Text style={styles.infoBody}>{tr('commentsInfoBody')}</Text>
        </View>
      </View>

      {items.length === 0 ? <Text style={styles.empty}>{tr('commentsEmpty')}</Text> : null}
      {items.map((item) => (
        <CommentCard
          key={item.id}
          item={item}
          untitled={tr('commentsUntitled')}
          onPress={() => onSelect(item.id)}
          tr={tr}
        />
      ))}

      <Text style={styles.footer}>{tr('commentsFooter')}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 12, paddingBottom: 28, flexGrow: 1 },
  info: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    backgroundColor: CM_TEAL_SOFT,
    borderRadius: CM_RADIUS,
    padding: 12,
  },
  infoIcon: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: CM_TEAL,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 1,
  },
  infoI: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '700' },
  infoCopy: { flex: 1, gap: 4 },
  infoTitle: {
    color: CM_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    fontWeight: '700',
  },
  infoBody: { color: CM_TEAL_DARK, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  empty: { color: CM_MUTED, fontFamily: fonts.body, fontSize: 14 },
  footer: {
    color: CM_MUTED,
    fontFamily: fonts.body,
    fontSize: 13,
    textAlign: 'center',
    marginTop: 'auto',
    paddingTop: 16,
    lineHeight: 18,
  },
});
