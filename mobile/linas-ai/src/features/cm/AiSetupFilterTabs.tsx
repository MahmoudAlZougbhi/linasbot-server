import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing } from '../../theme';
import { AI_SETUP_CARD_BORDER, AI_SETUP_ORANGE, AI_SETUP_TEAL } from './aiSetupDesign';

export type AiSetupFilter = 'all' | 'missing';

type Props = {
  filter: AiSetupFilter;
  missingCount: number;
  onChange: (filter: AiSetupFilter) => void;
};

/** All / Missing filter tabs matching AI Setup design handoff. */
export function AiSetupFilterTabs({ filter, missingCount, onChange }: Props) {
  const { tr } = useI18n();

  return (
    <View style={styles.row}>
      <Pressable
        onPress={() => onChange('all')}
        style={[
          styles.tab,
          filter === 'all' ? styles.tabSelected : styles.tabIdle,
          filter === 'all' ? { borderColor: AI_SETUP_TEAL } : { borderColor: AI_SETUP_CARD_BORDER },
        ]}
        accessibilityRole="button"
        accessibilityState={{ selected: filter === 'all' }}
        accessibilityLabel={tr('aiSetupFilterAll')}
      >
        <Text style={[styles.tabText, { color: filter === 'all' ? AI_SETUP_TEAL : '#8A9A98' }]}>
          {tr('aiSetupFilterAll')}
        </Text>
      </Pressable>

      <Pressable
        onPress={() => onChange('missing')}
        style={[
          styles.tab,
          filter === 'missing' ? styles.tabSelected : styles.tabIdle,
          filter === 'missing' ? { borderColor: AI_SETUP_TEAL } : { borderColor: AI_SETUP_CARD_BORDER },
        ]}
        accessibilityRole="button"
        accessibilityState={{ selected: filter === 'missing' }}
        accessibilityLabel={tr('aiSetupFilterMissing')}
      >
        <Text style={[styles.tabText, { color: filter === 'missing' ? AI_SETUP_TEAL : '#8A9A98' }]}>
          {tr('aiSetupFilterMissing')}
        </Text>
        {missingCount > 0 ? (
          <View style={styles.badge}>
            <Text style={styles.badgeText}>{missingCount}</Text>
          </View>
        ) : null}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: spacing.sm },
  tab: {
    flex: 1,
    minHeight: 44,
    borderRadius: radii.md,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
    backgroundColor: '#FFFFFF',
  },
  tabSelected: { backgroundColor: '#FFFFFF' },
  tabIdle: { backgroundColor: '#FFFFFF' },
  tabText: { fontFamily: fonts.bodyMedium, fontSize: 15 },
  badge: {
    minWidth: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: AI_SETUP_ORANGE,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  badgeText: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 12 },
});
