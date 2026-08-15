import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../../theme';
import { DASH_CARD_RADIUS, DASH_HAIRLINE, DASH_ICON_BG, DASH_NAVY } from '../dashboardChrome';
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
    icon: 'chatbox-ellipses-outline' as const,
  },
  {
    key: 'comments_replied' as const,
    labelKey: 'dashCommentsReplied' as const,
    icon: 'chatbubble-outline' as const,
  },
  {
    key: 'smart_answers' as const,
    labelKey: 'dashSmartAnswers' as const,
    icon: 'sparkles-outline' as const,
  },
  {
    key: 'requests' as const,
    labelKey: 'dashRequests' as const,
    icon: 'briefcase-outline' as const,
  },
];

export function TotalActivityGrid({ activity, unavailable }: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();

  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <Text style={styles.title}>{tr('dashTotalActivity')}</Text>
      <View style={styles.grid}>
        <View pointerEvents="none" style={styles.vRule} />
        <View pointerEvents="none" style={styles.hRule} />
        {TILES.map((tile) => {
          const value = activity?.[tile.key];
          return (
            <View key={tile.key} style={styles.cell}>
              <View style={styles.iconWrap}>
                <Ionicons name={tile.icon} size={20} color={DASH_NAVY} />
              </View>
              <View style={styles.copy}>
                <Text style={styles.value}>
                  {unavailable || value == null ? '—' : formatCount(value)}
                </Text>
                <Text style={styles.label}>{tr(tile.labelKey)}</Text>
              </View>
            </View>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: DASH_CARD_RADIUS,
    borderWidth: 1,
    overflow: 'hidden',
  },
  title: {
    color: DASH_NAVY,
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.sm,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    position: 'relative',
  },
  vRule: {
    position: 'absolute',
    left: '50%',
    top: 0,
    bottom: 0,
    width: StyleSheet.hairlineWidth,
    backgroundColor: DASH_HAIRLINE,
    zIndex: 1,
  },
  hRule: {
    position: 'absolute',
    top: '50%',
    left: 0,
    right: 0,
    height: StyleSheet.hairlineWidth,
    backgroundColor: DASH_HAIRLINE,
    zIndex: 1,
  },
  cell: {
    width: '50%',
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 18,
    paddingHorizontal: 16,
    gap: 10,
  },
  iconWrap: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: DASH_ICON_BG,
    alignItems: 'center',
    justifyContent: 'center',
  },
  copy: { flex: 1, gap: 2 },
  value: {
    color: DASH_NAVY,
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
  },
  label: {
    color: DASH_NAVY,
    fontFamily: fonts.body,
    fontSize: 12,
  },
});
