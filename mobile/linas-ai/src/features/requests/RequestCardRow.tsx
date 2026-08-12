import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { StatusChip } from '../../components/StatusChip';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import {
  CHANNEL_LABEL_KEYS,
  STATUS_LABEL_KEYS,
  TYPE_LABEL_KEYS,
  cardSummary,
  formatWhen,
  type RequestCard,
} from './requestsTypes';

type Props = {
  item: RequestCard;
  onPress: () => void;
};

function statusTone(status: string): 'neutral' | 'ok' | 'warn' | 'soon' {
  if (status === 'COMPLETED' || status === 'CONFIRMED' || status === 'READY') return 'ok';
  if (status === 'NEW' || status === 'WAITING_FOR_CUSTOMER') return 'warn';
  if (status === 'CANCELLED') return 'soon';
  return 'neutral';
}

export function RequestCardRow({ item, onPress }: Props) {
  const { colors } = useTheme();
  const { tr, language } = useI18n();
  const name =
    item.customer_display_name?.trim() ||
    item.platform_username?.trim() ||
    item.request_number;
  const typeKey = TYPE_LABEL_KEYS[item.request_type];
  const statusKey = STATUS_LABEL_KEYS[item.status];
  const channelKey = item.source_channel ? CHANNEL_LABEL_KEYS[item.source_channel] : null;
  const summary = cardSummary(item);
  const notifyFailed = item.notification_status === 'failed';

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.card,
        {
          backgroundColor: colors.surface,
          borderColor: colors.border,
          opacity: pressed ? 0.92 : 1,
        },
      ]}
      accessibilityRole="button"
      accessibilityLabel={name}
    >
      <View style={styles.top}>
        <Text style={[styles.name, { color: colors.text }]} numberOfLines={1}>
          {name}
        </Text>
        {notifyFailed ? (
          <View style={styles.failRow}>
            <AppIcon icon={feather('alert-circle')} size={14} color={colors.warning} />
            <Text style={[styles.fail, { color: colors.warning }]}>{tr('reqNotifyFailed')}</Text>
          </View>
        ) : null}
      </View>
      <View style={styles.chips}>
        {channelKey ? <StatusChip label={tr(channelKey)} /> : null}
        {typeKey ? <StatusChip label={tr(typeKey)} /> : null}
        {statusKey ? <StatusChip label={tr(statusKey)} tone={statusTone(item.status)} /> : null}
      </View>
      <Text style={[styles.meta, { color: colors.textMuted }]} numberOfLines={1}>
        {tr('reqNumber')}: {item.request_number}
      </Text>
      {summary ? (
        <Text style={[styles.summary, { color: colors.text }]} numberOfLines={2}>
          {summary}
        </Text>
      ) : null}
      <View style={styles.footer}>
        <Text style={[styles.meta, { color: colors.textDim }]}>
          {formatWhen(item.created_at, language)}
        </Text>
        <Text style={[styles.meta, { color: colors.textDim }]} numberOfLines={1}>
          {item.assigned_user_id ? item.assigned_user_id.slice(0, 8) : tr('reqUnassigned')}
        </Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderRadius: radii.lg,
    padding: spacing.lg,
    marginBottom: spacing.md,
    gap: spacing.sm,
  },
  top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  name: { flex: 1, fontFamily: fonts.bodyMedium, fontSize: 16 },
  failRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  fail: { fontFamily: fonts.body, fontSize: 11 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  summary: { fontFamily: fonts.body, fontSize: 14, lineHeight: 20 },
  meta: { fontFamily: fonts.body, fontSize: 12 },
  footer: { flexDirection: 'row', justifyContent: 'space-between', gap: 8 },
});
