import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import type { StringKey } from '../../i18n';
import { fonts } from '../../theme';
import { FAQ_BORDER, FAQ_ICON_SQ, FAQ_MUTED, FAQ_RADIUS_SM } from './faqChrome';

type Props = {
  count: number;
  query: string;
  onQueryChange: (value: string) => void;
  tr: (key: StringKey) => string;
};

export function FaqListToolbar({ count, query, onQueryChange, tr }: Props) {
  const [open, setOpen] = useState(Boolean(query));
  const showSearch = open || Boolean(query);

  return (
    <View style={styles.wrap}>
      <View style={styles.row}>
        <Text style={styles.count}>
          {count} {tr('faqAnswersCount')}
        </Text>
        <Pressable
          onPress={() => setOpen((v) => !v)}
          style={styles.searchSq}
          accessibilityRole="button"
          accessibilityLabel={tr('faqSearchA11y')}
        >
          <AppIcon icon={feather('search')} size={16} color={FAQ_MUTED} />
        </Pressable>
      </View>
      {showSearch ? (
        <TextInput
          value={query}
          onChangeText={onQueryChange}
          placeholder={tr('faqSearchPlaceholder')}
          placeholderTextColor={FAQ_MUTED}
          style={styles.input}
          autoCapitalize="none"
          autoCorrect={false}
          accessibilityLabel={tr('faqSearchA11y')}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 8 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  count: { color: FAQ_MUTED, fontFamily: fonts.body, fontSize: 14 },
  searchSq: {
    width: FAQ_ICON_SQ,
    height: FAQ_ICON_SQ,
    borderRadius: FAQ_RADIUS_SM,
    borderWidth: 1,
    borderColor: FAQ_BORDER,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FFFFFF',
  },
  input: {
    backgroundColor: '#FFFFFF',
    borderRadius: FAQ_RADIUS_SM,
    borderWidth: 1,
    borderColor: FAQ_BORDER,
    color: '#0F172A',
    fontFamily: fonts.body,
    fontSize: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
});
