import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../../theme';
import { formatCount } from '../dashboardFormat';
import type { TenantDashboard } from '../dashboardTypes';

type Activity = NonNullable<TenantDashboard['activity_summary']['total_activity']>;

type Props = {
  activity: Activity | undefined;
  unavailable?: boolean;
};

const TILES = [
  {
    key: 'messages_replied' as const,
    labelKey: 'dashMessagesReplied' as const,
    icon: 'chatbubble-outline' as const,
    bg: '#CCFBF1',
    fg: '#0D9488',
  },
  {
    key: 'comments_replied' as const,
    labelKey: 'dashCommentsReplied' as const,
    icon: 'chatbubbles-outline' as const,
    bg: '#DBEAFE',
    fg: '#3B82F6',
  },
  {
    key: 'smart_answers' as const,
    labelKey: 'dashSmartAnswers' as const,
    icon: 'sparkles' as const,
    bg: '#CCFBF1',
    fg: '#0F766E',
  },
  {
    key: 'requests' as const,
    labelKey: 'dashRequests' as const,
    icon: 'briefcase-outline' as const,
    bg: '#FEF3C7',
    fg: '#B45309',
  },
];

export function TotalActivityGrid({ activity, unavailable }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();

  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <Text style={[styles.title, { color: colors.text }]}>{tr('dashTotalActivity')}</Text>
      <View style={[styles.grid, { borderColor: colors.borderSoft }]}>
        {TILES.map((tile, index) => {
          const value = unavailable || !activity ? '—' : formatCount(activity[tile.key]);
          const isRight = index % 2 === 1;
          const isBottom = index >= 2;
          return (
            <View
              key={tile.key}
              style={[
                styles.cell,
                isRight && [styles.cellRight, { borderLeftColor: colors.borderSoft }],
                isBottom && [styles.cellBottom, { borderTopColor: colors.borderSoft }],
              ]}
            >
              <View style={[styles.iconWrap, { backgroundColor: tile.bg }]}>
                <Ionicons name={tile.icon} size={18} color={tile.fg} />
              </View>
              <Text style={[styles.value, { color: colors.text }]}>{value}</Text>
              <Text style={[styles.label, { color: colors.textMuted }]}>{tr(tile.labelKey)}</Text>
            </View>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radii.lg, borderWidth: 1, padding: spacing.lg, gap: spacing.md },
  title: { fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', borderRadius: radii.md, overflow: 'hidden' },
  cell: { width: '50%', padding: spacing.md, gap: 6, alignItems: 'center' },
  cellRight: { borderLeftWidth: 1 },
  cellBottom: { borderTopWidth: 1 },
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  value: { fontFamily: fonts.bodyMedium, fontSize: 22, fontWeight: '700' },
  label: { fontFamily: fonts.body, fontSize: 12, textAlign: 'center' },
});
