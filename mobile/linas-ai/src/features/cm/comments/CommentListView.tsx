import { StyleSheet, Text, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../../components/AppIcon';
import { LinasSparkleIcon } from '../../../components/LinasSparkleIcon';
import { PrimaryButton } from '../../../components/PrimaryButton';
import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { CommentCard } from './CommentCard';
import {
  CM_BORDER,
  CM_MUTED,
  CM_RADIUS,
  CM_TEAL,
  CM_TEAL_DARK,
  CM_TEAL_SOFT,
} from './commentChrome';
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
  return (
    <View style={styles.wrap}>
      <View style={styles.hero}>
        <LinasSparkleIcon size={22} color={CM_TEAL} />
        <Text style={styles.title}>{tr('aiSetupSec_comments')}</Text>
        <Text style={styles.subtitle}>{tr('commentsSubtitle')}</Text>
      </View>

      <PrimaryButton label={tr('commentsAdd')} onPress={onAdd} style={styles.addBtn} />

      <View style={styles.info}>
        <View style={styles.infoIcon}>
          <Text style={styles.infoI}>i</Text>
        </View>
        <View style={styles.infoCopy}>
          <Text style={styles.infoTitle}>{tr('commentsInfoTitle')}</Text>
          <Text style={styles.infoBody}>{tr('commentsInfoBody')}</Text>
        </View>
      </View>

      <View style={styles.search}>
        <AppIcon icon={feather('search')} size={18} color={CM_MUTED} />
        <TextInput
          value={query}
          onChangeText={onQueryChange}
          placeholder={tr('commentsSearch')}
          placeholderTextColor={CM_MUTED}
          style={styles.searchInput}
          autoCapitalize="none"
          autoCorrect={false}
          accessibilityLabel={tr('commentsSearch')}
        />
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
  hero: { alignItems: 'center', gap: 6, marginTop: 4 },
  title: {
    color: CM_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 28,
    fontWeight: '700',
  },
  subtitle: { color: CM_MUTED, fontFamily: fonts.body, fontSize: 15, textAlign: 'center' },
  addBtn: { backgroundColor: CM_TEAL, borderRadius: CM_RADIUS },
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
  search: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: CM_BORDER,
    borderRadius: CM_RADIUS,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  searchInput: {
    flex: 1,
    color: CM_TEAL_DARK,
    fontFamily: fonts.body,
    fontSize: 15,
    padding: 0,
  },
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
