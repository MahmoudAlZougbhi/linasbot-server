import { useEffect, useMemo, useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { formatShortDate } from './requestsFormat';

const DOW = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

type FieldProps = {
  label: string;
  value: string | null;
  onChange: (ymd: string) => void;
};

type PickerProps = {
  visible: boolean;
  title: string;
  value: string | null;
  onPick: (ymd: string) => void;
  onClose: () => void;
};

type MonthCalendarProps = {
  value: string | null;
  onPick: (ymd: string) => void;
  locale?: string;
};

function toYmd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function parseYmd(ymd: string): Date {
  return new Date(`${ymd.slice(0, 10)}T12:00:00`);
}

function monthCells(year: number, month: number): (number | null)[] {
  const first = new Date(year, month, 1);
  const pad = first.getDay();
  const days = new Date(year, month + 1, 0).getDate();
  return [...Array(pad).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
}

export function RequestDateField({ label, value, onChange }: FieldProps) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Pressable
        onPress={() => setOpen(true)}
        style={[styles.field, { borderColor: colors.border, backgroundColor: colors.surface }]}
        accessibilityRole="button"
        accessibilityLabel={label}
      >
        <View style={styles.fieldText}>
          <Text style={[styles.fieldLabel, { color: colors.textMuted }]}>{label}</Text>
          <Text style={{ color: value ? colors.text : colors.textDim, fontFamily: fonts.body, fontSize: 15 }}>
            {value ? formatShortDate(value, 'en') : ''}
          </Text>
        </View>
        <AppIcon icon={feather('calendar')} size={16} color={colors.textMuted} />
      </Pressable>
      <RequestDatePicker
        visible={open}
        title={label}
        value={value}
        onPick={(ymd) => {
          onChange(ymd);
          setOpen(false);
        }}
        onClose={() => setOpen(false)}
      />
    </>
  );
}

/** Month grid from the existing request picker — day + month + year via month chevrons. */
export function RequestMonthCalendar({ value, onPick, locale = 'en-US' }: MonthCalendarProps) {
  const { colors } = useTheme();
  const initial = value ? parseYmd(value) : new Date();
  const [cursor, setCursor] = useState(initial);

  useEffect(() => {
    setCursor(value ? parseYmd(value) : new Date());
  }, [value]);

  const year = cursor.getFullYear();
  const month = cursor.getMonth();
  const cells = useMemo(() => monthCells(year, month), [year, month]);
  const heading = cursor.toLocaleDateString(locale, { month: 'long', year: 'numeric' });

  return (
    <View>
      <View style={styles.monthRow}>
        <Pressable
          onPress={() => setCursor(new Date(year, month - 1, 1))}
          accessibilityRole="button"
          accessibilityLabel="Previous month"
        >
          <AppIcon icon={feather('chevron-left')} size={20} color={colors.accent} />
        </Pressable>
        <Text style={[styles.month, { color: colors.text }]}>{heading}</Text>
        <Pressable
          onPress={() => setCursor(new Date(year, month + 1, 1))}
          accessibilityRole="button"
          accessibilityLabel="Next month"
        >
          <AppIcon icon={feather('chevron-right')} size={20} color={colors.accent} />
        </Pressable>
      </View>
      <View style={styles.grid} accessibilityLabel="Date calendar">
        {DOW.map((d, i) => (
          <Text key={`${d}-${i}`} style={[styles.dow, { color: colors.textMuted }]}>
            {d}
          </Text>
        ))}
        {cells.map((day, i) => {
          if (day == null) return <View key={`e-${i}`} style={styles.cell} />;
          const ymd = toYmd(new Date(year, month, day));
          const on = ymd === value;
          return (
            <Pressable
              key={ymd}
              onPress={() => onPick(ymd)}
              style={[styles.cell, on && { backgroundColor: colors.accent, borderRadius: 18 }]}
              accessibilityRole="button"
              accessibilityState={{ selected: on }}
            >
              <Text style={{ color: on ? colors.onAccent : colors.text, fontFamily: fonts.bodyMedium }}>
                {day}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

export function RequestDatePicker({ visible, title, value, onPick, onClose }: PickerProps) {
  const { colors } = useTheme();

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable
          style={[styles.sheet, { backgroundColor: colors.surface }]}
          onPress={(e) => e.stopPropagation()}
        >
          <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
          <RequestMonthCalendar key={visible ? 'open' : 'closed'} value={value} onPick={onPick} />
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  field: {
    flex: 1,
    minHeight: 52,
    borderWidth: 1,
    borderRadius: radii.sm,
    paddingHorizontal: 10,
    paddingVertical: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  fieldText: { flex: 1, gap: 1 },
  fieldLabel: { fontFamily: fonts.body, fontSize: 12 },
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.45)',
    justifyContent: 'center',
    padding: spacing.lg,
  },
  sheet: {
    borderRadius: radii.md,
    padding: spacing.lg,
  },
  title: { fontFamily: fonts.bodyMedium, fontSize: 17, fontWeight: '700', marginBottom: spacing.md },
  monthRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  month: { fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '600' },
  grid: { flexDirection: 'row', flexWrap: 'wrap' },
  dow: {
    width: '14.28%',
    textAlign: 'center',
    fontFamily: fonts.body,
    fontSize: 12,
    marginBottom: 6,
  },
  cell: {
    width: '14.28%',
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
