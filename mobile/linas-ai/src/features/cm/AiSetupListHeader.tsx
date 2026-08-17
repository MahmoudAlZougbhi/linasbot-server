import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { fonts } from '../../theme';
import { AI_SETUP_TEAL } from './aiSetupDesign';

const TEAL_DARK = '#0F4C4A';
const MUTED = '#94A3B8';
const BORDER = '#E2E8F0';
const RADIUS = 12;

type Props = {
  query: string;
  onQueryChange: (value: string) => void;
  searchPlaceholder: string;
  addA11yLabel: string;
  onAdd: () => void;
  countLabel?: string;
};

/** First-open AI Setup list chrome: search + teal add square, count. Title lives in ScreenChrome. */
export function AiSetupListHeader({
  query,
  onQueryChange,
  searchPlaceholder,
  addA11yLabel,
  onAdd,
  countLabel,
}: Props) {
  return (
    <View style={styles.wrap}>
      <View style={styles.searchRow}>
        <View style={styles.search}>
          <AppIcon icon={feather('search')} size={18} color={MUTED} />
          <TextInput
            value={query}
            onChangeText={onQueryChange}
            placeholder={searchPlaceholder}
            placeholderTextColor={MUTED}
            style={styles.searchInput}
            autoCapitalize="none"
            autoCorrect={false}
            accessibilityLabel={searchPlaceholder}
          />
        </View>
        <Pressable
          onPress={onAdd}
          accessibilityRole="button"
          accessibilityLabel={addA11yLabel}
          style={({ pressed }) => [styles.addSq, pressed && styles.pressed]}
        >
          <AppIcon icon={feather('plus')} size={22} color="#FFFFFF" />
        </Pressable>
      </View>
      {countLabel ? <Text style={styles.count}>{countLabel}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 12 },
  searchRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  search: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: BORDER,
    borderRadius: RADIUS,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  searchInput: {
    flex: 1,
    color: TEAL_DARK,
    fontFamily: fonts.body,
    fontSize: 15,
    padding: 0,
  },
  addSq: {
    width: 48,
    height: 48,
    borderRadius: RADIUS,
    backgroundColor: AI_SETUP_TEAL,
    alignItems: 'center',
    justifyContent: 'center',
  },
  count: { color: MUTED, fontFamily: fonts.body, fontSize: 13, marginTop: 4 },
  pressed: { opacity: 0.7 },
});
