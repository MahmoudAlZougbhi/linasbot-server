import type { RefObject } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { AppIcon } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../theme';
import { DRAWER_TOOL_ICONS } from './moduleIcons';

type Props = {
  searchOpen: boolean;
  query: string;
  searchRef: RefObject<TextInput | null>;
  onOpenSearch: () => void;
  onCloseSearch: () => void;
  onChangeQuery: (value: string) => void;
};

export function DrawerHeader({
  searchOpen,
  query,
  searchRef,
  onOpenSearch,
  onCloseSearch,
  onChangeQuery,
}: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();

  return (
    <View style={styles.wrap}>
      {searchOpen ? (
        <View
          style={[
            styles.searchExpanded,
            { backgroundColor: colors.input, borderColor: colors.border },
          ]}
        >
          <AppIcon icon={DRAWER_TOOL_ICONS.search} size={18} color={colors.accentDeep} />
          <TextInput
            ref={searchRef}
            value={query}
            onChangeText={onChangeQuery}
            placeholder={tr('searchChats')}
            placeholderTextColor={colors.textDim}
            style={[styles.searchInput, { color: colors.text }]}
            accessibilityLabel={tr('searchConversationTitles')}
            returnKeyType="search"
            clearButtonMode="while-editing"
            autoCorrect={false}
            autoCapitalize="none"
          />
          <Pressable
            onPress={onCloseSearch}
            accessibilityRole="button"
            accessibilityLabel="Close search"
            hitSlop={8}
            style={styles.searchClear}
          >
            <AppIcon icon={DRAWER_TOOL_ICONS.close} size={16} color={colors.textMuted} />
          </Pressable>
        </View>
      ) : (
        <View style={styles.headerRow}>
          <View style={styles.brandRow} accessibilityRole="header">
            <Text style={[styles.sparkle, { color: colors.accentDeep }]}>✦</Text>
            <Text style={[styles.wordmark, { color: colors.accentDeep }]}>Linas</Text>
          </View>
          <Pressable
            onPress={onOpenSearch}
            accessibilityRole="button"
            accessibilityLabel={tr('searchChats')}
            hitSlop={10}
            style={styles.searchHit}
          >
            <AppIcon icon={DRAWER_TOOL_ICONS.search} size={20} color={colors.accentDeep} />
          </Pressable>
        </View>
      )}

      {!searchOpen ? (
        <View style={styles.separatorRow}>
          <View style={[styles.separatorLine, { backgroundColor: colors.border }]} />
          <Text style={[styles.separatorSparkle, { color: colors.textDim }]}>✦</Text>
          <View style={[styles.separatorLine, { backgroundColor: colors.border }]} />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: spacing.md, gap: spacing.md },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 36,
  },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sparkle: { fontSize: 18, lineHeight: 20 },
  wordmark: { fontFamily: fonts.bodyMedium, fontWeight: '700', fontSize: 20 },
  searchHit: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  separatorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  separatorLine: { flex: 1, height: StyleSheet.hairlineWidth },
  separatorSparkle: { fontSize: 10, lineHeight: 12 },
  searchExpanded: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
    borderRadius: 999,
    minHeight: 40,
    paddingHorizontal: 12,
  },
  searchInput: {
    flex: 1,
    minHeight: 36,
    paddingVertical: 6,
    fontSize: 15,
  },
  searchClear: {
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
