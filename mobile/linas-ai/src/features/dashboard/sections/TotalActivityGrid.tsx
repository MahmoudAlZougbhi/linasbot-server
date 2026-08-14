import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../../theme';
import { DASH_CARD_RADIUS, DASH_ICON_BG } from '../dashboardChrome';
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
  },
  {
    key: 'comments_replied' as const,
    labelKey: 'dashCommentsReplied' as const,
    icon: 'chatbubbles-outline' as const,
  },
  {
    key: 'smart_answers' as const,
    labelKey: 'dashSmartAnswers' as const,
    icon: 'sparkles-outline' as const,
  },
  {
    key: 'requests' as const,
    labelKey: 'dashRequests' as const,
    icon: 'bag-handle-outline' as const,
  },
];

export function TotalActivityGrid({ activity, unavailable }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();

  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <Text style={[styles.title, { color: colors.text }]}>{tr('dashTotalActivity')}</Text>
      <View style={styles.grid}>
        {TILES.map((tile, index) => {
          const value = unavailable || !activity ? 0 : activity[tile.key];
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
              <View style={styles.iconWrap}>
                <Ionicons name={tile.icon} size={18} color={colors.textMuted} />
              </View>
              <Text style={[styles.value, { color: colors.text }]}>
                {unavailable ? '—' : formatCount(value)}
              </Text>
              <Text style={[styles.label, { color: colors.textMuted }]}>{tr(tile.labelKey)}</Text>
            </View>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: DASH_CARD_RADIUS, borderWidth: 1, padding: spacing.lg, gap: spacing.md },
  title: { fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  grid: { flexDirection: 'row', flexWrap: 'wrap' },
  cell: { width: '50%', paddingVertical: spacing.md, gap: 6, alignItems: 'center' },
  cellRight: { borderLeftWidth: StyleSheet.hairlineWidth },
  cellBottom: { borderTopWidth: StyleSheet.hairlineWidth },
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: DASH_ICON_BG,
    alignItems: 'center',
    justifyContent: 'center',
  },
  value: { fontFamily: fonts.bodyMedium, fontSize: 22, fontWeight: '700' },
  label: { fontFamily: fonts.body, fontSize: 12, textAlign: 'center' },
});
