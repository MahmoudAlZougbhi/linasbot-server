import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { fonts, radii, useTheme } from '../../theme';
import { RequestPickSheet } from './RequestPickSheet';
import { statusBucket } from './requestsFormat';
import type { RequestCard, StatusBucket } from './requestsTypes';
import type { StaffPick } from './useRequestsList';

const STATUS_OPTIONS: { id: StatusBucket; label: string }[] = [
  { id: 'new', label: 'New' },
  { id: 'in_progress', label: 'In progress' },
  { id: 'done', label: 'Done' },
];

type Props = {
  item: RequestCard;
  assigneeLabel: string;
  staff: StaffPick[];
  busy: boolean;
  onStatus: (bucket: StatusBucket) => void;
  onAssign: (userId: string | null) => void;
  onChat: () => void;
  onPrint: () => void;
};

export function RequestCardActions({
  item,
  assigneeLabel,
  staff,
  busy,
  onStatus,
  onAssign,
  onChat,
  onPrint,
}: Props) {
  const { colors } = useTheme();
  const [statusOpen, setStatusOpen] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const bucket = statusBucket(item.status);
  const statusLabel =
    bucket === 'new' ? 'New' : bucket === 'done' ? 'Done' : bucket === 'cancelled' ? 'Cancelled' : 'In progress';

  return (
    <View style={styles.row}>
      <Pressable
        onPress={() => setStatusOpen(true)}
        disabled={busy}
        style={[styles.status, { backgroundColor: colors.accentSoft }]}
        accessibilityRole="button"
        accessibilityLabel={`Status ${statusLabel}`}
      >
        <Text style={[styles.statusText, { color: colors.accentDeep }]} numberOfLines={1}>
          {statusLabel}
        </Text>
        <AppIcon icon={feather('chevron-down')} size={14} color={colors.accentDeep} />
      </Pressable>
      <Pressable
        onPress={() => setAssignOpen(true)}
        disabled={busy}
        style={styles.assign}
        accessibilityRole="button"
        accessibilityLabel={assigneeLabel}
      >
        <AppIcon icon={feather('user')} size={14} color={colors.textMuted} />
        <Text style={[styles.assignText, { color: colors.text }]} numberOfLines={1}>
          {assigneeLabel}
        </Text>
        <AppIcon icon={feather('chevron-down')} size={14} color={colors.textMuted} />
      </Pressable>
      <OutlineBtn label="Chat" icon="message-circle" onPress={onChat} disabled={busy} />
      <OutlineBtn label="Print" icon="printer" onPress={onPrint} disabled={busy} />

      <RequestPickSheet
        visible={statusOpen}
        title="Status"
        selectedId={bucket === 'cancelled' ? '' : bucket}
        options={STATUS_OPTIONS}
        onPick={(id) => onStatus(id as StatusBucket)}
        onClose={() => setStatusOpen(false)}
      />
      <RequestPickSheet
        visible={assignOpen}
        title="Assign"
        selectedId={item.assigned_user_id ?? ''}
        options={[{ id: '', label: 'Unassigned' }, ...staff]}
        onPick={(id) => onAssign(id || null)}
        onClose={() => setAssignOpen(false)}
      />
    </View>
  );
}

function OutlineBtn({
  label,
  icon,
  onPress,
  disabled,
}: {
  label: string;
  icon: 'message-circle' | 'printer';
  onPress: () => void;
  disabled: boolean;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={[styles.outline, { borderColor: colors.accent }]}
      accessibilityRole="button"
      accessibilityLabel={label}
    >
      <AppIcon icon={feather(icon)} size={14} color={colors.accent} />
      <Text style={[styles.outlineText, { color: colors.accent }]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginTop: 4 },
  status: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    borderRadius: radii.sm,
    paddingHorizontal: 10,
    paddingVertical: 8,
    minHeight: 36,
  },
  statusText: { fontFamily: fonts.bodyMedium, fontSize: 13 },
  assign: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 8, minHeight: 36, maxWidth: 110 },
  assignText: { fontFamily: fonts.bodyMedium, fontSize: 13, flexShrink: 1 },
  outline: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    borderWidth: 1.5,
    borderRadius: radii.sm,
    paddingHorizontal: 10,
    paddingVertical: 8,
    minHeight: 36,
  },
  outlineText: { fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '600' },
});
