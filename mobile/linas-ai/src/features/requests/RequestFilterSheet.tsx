import { useEffect, useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { PlatformChannelIcon } from '../livechat/PlatformChannelIcon';
import type { ChatChannel } from '../livechat/liveChatTypes';
import { FILTER_PLATFORMS, formatShortDate } from './requestsFormat';
import { RequestPickSheet } from './RequestPickSheet';
import type { RequestFilters, StaffPick } from './useRequestsList';
import { previewMatchedCount } from './useRequestsList';

type Props = {
  visible: boolean;
  applied: RequestFilters;
  staff: StaffPick[];
  search: string;
  onClose: () => void;
  onApply: (next: RequestFilters) => void;
};

function shiftDay(ymd: string | null, delta: number): string {
  const base = ymd ? new Date(`${ymd.slice(0, 10)}T12:00:00`) : new Date();
  base.setDate(base.getDate() + delta);
  return base.toISOString().slice(0, 10);
}

export function RequestFilterSheet({ visible, applied, staff, search, onClose, onApply }: Props) {
  const { colors } = useTheme();
  const [draft, setDraft] = useState<RequestFilters>(applied);
  const [matched, setMatched] = useState(0);
  const [assignOpen, setAssignOpen] = useState(false);

  useEffect(() => {
    if (visible) setDraft(applied);
  }, [visible, applied]);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    const t = setTimeout(() => {
      void previewMatchedCount(draft, search)
        .then((n) => {
          if (!cancelled) setMatched(n);
        })
        .catch(() => {
          if (!cancelled) setMatched(0);
        });
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [visible, draft, search]);

  const platforms = draft.platforms;
  const allSelected = platforms.length === 0;
  const assignee =
    staff.find((s) => s.id === draft.assignedUserId)?.label ||
    (draft.assignedUserId ? 'Assigned' : 'All users');

  function togglePlatform(id: string) {
    if (id === 'all') {
      setDraft((prev) => ({ ...prev, platforms: [] }));
      return;
    }
    setDraft((prev) => {
      const has = prev.platforms.includes(id);
      const next = has ? prev.platforms.filter((p) => p !== id) : [...prev.platforms, id];
      return { ...prev, platforms: next };
    });
  }

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable
          style={[styles.sheet, { backgroundColor: colors.surface }]}
          onPress={(e) => e.stopPropagation()}
        >
          <View style={[styles.handle, { backgroundColor: colors.border }]} />
          <View style={styles.header}>
            <Text style={[styles.title, { color: colors.text }]}>Filter requests</Text>
            <Pressable onPress={onClose} accessibilityRole="button" accessibilityLabel="Close">
              <AppIcon icon={feather('x')} size={20} color={colors.text} />
            </Pressable>
          </View>

          <Text style={[styles.section, { color: colors.textMuted }]}>Platforms</Text>
          <View style={styles.chips}>
            {FILTER_PLATFORMS.map((p) => {
              const selected = p.id === 'all' ? allSelected : platforms.includes(p.id);
              return (
                <Pressable
                  key={p.id}
                  onPress={() => togglePlatform(p.id)}
                  style={[
                    styles.chip,
                    {
                      borderColor: selected ? colors.accent : colors.border,
                      backgroundColor: colors.surface,
                    },
                  ]}
                >
                  {p.channel === 'all' ? (
                    <AppIcon icon={feather('globe')} size={16} color={colors.textMuted} />
                  ) : (
                    <PlatformChannelIcon channel={p.channel as ChatChannel} size={22} />
                  )}
                  <Text style={[styles.chipLabel, { color: colors.text }]}>
                    {p.id === 'all' ? 'All' : p.channel === 'facebook' ? 'Facebook' : labelFor(p.channel)}
                  </Text>
                  {selected && p.id !== 'all' ? (
                    <AppIcon icon={feather('check')} size={14} color={colors.accent} />
                  ) : null}
                </Pressable>
              );
            })}
          </View>

          <Text style={[styles.section, { color: colors.textMuted }]}>Date range</Text>
          <View style={styles.dates}>
            <DateField
              placeholder="From"
              value={draft.dateFrom}
              onShift={(d) => setDraft((prev) => ({ ...prev, dateFrom: shiftDay(prev.dateFrom, d) }))}
            />
            <DateField
              placeholder="To"
              value={draft.dateTo}
              onShift={(d) => setDraft((prev) => ({ ...prev, dateTo: shiftDay(prev.dateTo, d) }))}
            />
          </View>

          <Text style={[styles.section, { color: colors.textMuted }]}>Assigned user</Text>
          <Pressable
            onPress={() => setAssignOpen(true)}
            style={[styles.assign, { borderColor: colors.border }]}
          >
            <AppIcon icon={feather('user')} size={16} color={colors.textMuted} />
            <Text style={[styles.assignLabel, { color: colors.text }]}>{assignee}</Text>
            <AppIcon icon={feather('chevron-down')} size={16} color={colors.textMuted} />
          </Pressable>

          <View style={styles.footer}>
            <Pressable
              onPress={() => setDraft({ platforms: [], dateFrom: null, dateTo: null, assignedUserId: null })}
            >
              <Text style={[styles.reset, { color: colors.accent }]}>Reset</Text>
            </Pressable>
            <Pressable
              onPress={() => {
                onApply(draft);
                onClose();
              }}
              style={[styles.show, { backgroundColor: colors.accent }]}
            >
              <Text style={[styles.showLabel, { color: colors.onAccent }]}>
                {`Show ${matched} requests`}
              </Text>
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
      <RequestPickSheet
        visible={assignOpen}
        title="Assigned user"
        selectedId={draft.assignedUserId ?? ''}
        options={[{ id: '', label: 'All users' }, ...staff]}
        onPick={(id) => setDraft((prev) => ({ ...prev, assignedUserId: id || null }))}
        onClose={() => setAssignOpen(false)}
      />
    </Modal>
  );
}

function labelFor(channel: string): string {
  if (channel === 'whatsapp') return 'WhatsApp';
  if (channel === 'instagram') return 'Instagram';
  if (channel === 'tiktok') return 'TikTok';
  return 'Facebook';
}

function DateField({
  placeholder,
  value,
  onShift,
}: {
  placeholder: string;
  value: string | null;
  onShift: (delta: number) => void;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={() => onShift(value ? 1 : 0)}
      onLongPress={() => onShift(-1)}
      style={[styles.dateField, { borderColor: colors.border }]}
    >
      <Text style={{ color: value ? colors.text : colors.textDim, fontFamily: fonts.body, fontSize: 14, flex: 1 }}>
        {value ? formatShortDate(value, 'en') : placeholder}
      </Text>
      <AppIcon icon={feather('calendar')} size={16} color={colors.textMuted} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' },
  sheet: {
    borderTopLeftRadius: radii.xl,
    borderTopRightRadius: radii.xl,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xxl,
  },
  handle: { width: 36, height: 4, borderRadius: 2, alignSelf: 'center', marginTop: 10, marginBottom: 8 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.md },
  title: { fontFamily: fonts.bodyMedium, fontSize: 18, fontWeight: '700' },
  section: { fontFamily: fonts.body, fontSize: 13, marginBottom: 8, marginTop: 4 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: spacing.md },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderWidth: 1.5,
    borderRadius: radii.sm,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  chipLabel: { fontFamily: fonts.bodyMedium, fontSize: 13 },
  dates: { flexDirection: 'row', gap: 8, marginBottom: spacing.md },
  dateField: {
    flex: 1,
    minHeight: 44,
    borderWidth: 1,
    borderRadius: radii.sm,
    paddingHorizontal: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  assign: {
    minHeight: 44,
    borderWidth: 1,
    borderRadius: radii.sm,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: spacing.lg,
  },
  assignLabel: { flex: 1, fontFamily: fonts.bodyMedium, fontSize: 15 },
  footer: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  reset: { fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '600' },
  show: { borderRadius: radii.sm, paddingHorizontal: 18, paddingVertical: 12, minWidth: 168, alignItems: 'center' },
  showLabel: { fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
});
