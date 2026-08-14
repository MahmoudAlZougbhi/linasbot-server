import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, radii, spacing, useTheme } from '../../theme';
import { PlatformChannelIcon } from '../livechat/PlatformChannelIcon';
import { RequestCardActions } from './RequestCardActions';
import { cardSummary, formatPhone, formatRequestWhen, requestChannel } from './requestsFormat';
import type { RequestCard, StatusBucket } from './requestsTypes';
import type { StaffPick } from './useRequestsList';

type Props = {
  item: RequestCard;
  assigneeLabel: string;
  staff: StaffPick[];
  busy: boolean;
  language: string;
  onOpen: () => void;
  onStatus: (bucket: StatusBucket) => void;
  onAssign: (userId: string | null) => void;
  onChat: () => void;
  onPrint: () => void;
};

export function RequestCardRow({
  item,
  assigneeLabel,
  staff,
  busy,
  language,
  onOpen,
  onStatus,
  onAssign,
  onChat,
  onPrint,
}: Props) {
  const { colors } = useTheme();
  const name =
    item.customer_display_name?.trim() ||
    item.platform_username?.trim() ||
    item.request_number;
  const phone = formatPhone(item.phone_normalized);
  const when = formatRequestWhen(item.created_at, language);
  const meta = [phone, when].filter(Boolean).join(' · ');
  const summary = cardSummary(item);

  return (
    <Pressable
      onPress={onOpen}
      style={({ pressed }) => [
        styles.card,
        { backgroundColor: colors.surface, borderColor: colors.border, opacity: pressed ? 0.96 : 1 },
      ]}
      accessibilityRole="button"
      accessibilityLabel={name}
    >
      <Text style={[styles.number, { color: colors.accent }]}>{`Request #${item.request_number}`}</Text>
      <View style={styles.identity}>
        <PlatformChannelIcon channel={requestChannel(item.source_channel)} size={36} />
        <View style={styles.identityText}>
          <Text style={[styles.name, { color: colors.text }]} numberOfLines={1}>
            {name}
          </Text>
          {meta ? (
            <Text style={[styles.meta, { color: colors.textMuted }]} numberOfLines={1}>
              {meta}
            </Text>
          ) : null}
        </View>
      </View>
      {summary ? (
        <Text style={[styles.summary, { color: colors.text }]} numberOfLines={2}>
          {summary}
        </Text>
      ) : null}
      <RequestCardActions
        item={item}
        assigneeLabel={assigneeLabel}
        staff={staff}
        busy={busy}
        onStatus={onStatus}
        onAssign={onAssign}
        onChat={onChat}
        onPrint={onPrint}
      />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderRadius: radii.sm,
    padding: spacing.md,
    marginBottom: spacing.md,
    gap: 8,
  },
  number: { fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '600' },
  identity: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  identityText: { flex: 1, minWidth: 0, gap: 2 },
  name: { fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  meta: { fontFamily: fonts.body, fontSize: 13 },
  summary: { fontFamily: fonts.body, fontSize: 14, lineHeight: 20 },
});
