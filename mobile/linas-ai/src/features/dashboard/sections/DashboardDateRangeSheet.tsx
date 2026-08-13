import { useEffect, useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../../theme';
import type { ThemeColors } from '../../../theme/colors';
import type { DashboardPeriodSelection } from '../dashboardFormat';
import { monthStartIso, todayIso } from '../dashboardFormat';

type Props = {
  open: boolean;
  period: DashboardPeriodSelection;
  onClose: () => void;
  onApply: (next: DashboardPeriodSelection) => void;
};

type Preset = {
  id: 'billing' | '7d' | '30d';
  labelKey: 'dashBillingPeriod' | 'dashLast7Days' | 'dashLast30Days';
};

const PRESETS: Preset[] = [
  { id: 'billing', labelKey: 'dashBillingPeriod' },
  { id: '7d', labelKey: 'dashLast7Days' },
  { id: '30d', labelKey: 'dashLast30Days' },
];

function shiftDay(iso: string, delta: number): string {
  const dt = new Date(`${iso.slice(0, 10)}T12:00:00`);
  dt.setDate(dt.getDate() + delta);
  return dt.toISOString().slice(0, 10);
}

export function DashboardDateRangeSheet({ open, period, onClose, onApply }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const [start, setStart] = useState(monthStartIso());
  const [end, setEnd] = useState(todayIso());

  useEffect(() => {
    if (!open) return;
    if (period.kind === 'custom') {
      setStart(period.start);
      setEnd(period.end);
    } else {
      setStart(monthStartIso());
      setEnd(todayIso());
    }
  }, [open, period]);

  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable
          style={[styles.sheet, { backgroundColor: colors.surface, borderColor: colors.border }]}
          onPress={(e) => e.stopPropagation()}
        >
          <Text style={[styles.title, { color: colors.text }]}>{tr('dashSelectRange')}</Text>

          <View style={styles.presets}>
            {PRESETS.map((preset) => {
              const active = period.kind === 'preset' && period.id === preset.id;
              return (
                <Pressable
                  key={preset.id}
                  onPress={() => onApply({ kind: 'preset', id: preset.id })}
                  style={[
                    styles.chip,
                    {
                      backgroundColor: active ? colors.accentSoft : colors.surfaceAlt,
                      borderColor: active ? colors.accent : colors.border,
                    },
                  ]}
                >
                  <Text style={{ color: active ? colors.accentDeep : colors.text, fontFamily: fonts.bodyMedium }}>
                    {tr(preset.labelKey)}
                  </Text>
                </Pressable>
              );
            })}
          </View>

          <Text style={[styles.section, { color: colors.textMuted }]}>{tr('dashCustomRange')}</Text>
          <DateStepper label="Start" value={start} onChange={setStart} colors={colors} />
          <DateStepper label="End" value={end} onChange={setEnd} colors={colors} />

          <Pressable
            onPress={() => onApply({ kind: 'custom', start, end })}
            style={[styles.apply, { backgroundColor: colors.accent }]}
          >
            <Text style={{ color: colors.onAccent, fontFamily: fonts.bodyMedium }}>{tr('dashApplyRange')}</Text>
          </Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function DateStepper({
  label,
  value,
  onChange,
  colors,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  colors: ThemeColors;
}) {
  return (
    <View style={[styles.stepper, { borderColor: colors.border, backgroundColor: colors.surfaceAlt }]}>
      <Text style={{ color: colors.text, fontFamily: fonts.bodyMedium, width: 48 }}>{label}</Text>
      <Pressable onPress={() => onChange(shiftDay(value, -1))} style={styles.stepBtn}>
        <Text style={{ color: colors.text, fontSize: 18 }}>−</Text>
      </Pressable>
      <Text style={{ color: colors.text, fontFamily: fonts.bodyMedium, flex: 1, textAlign: 'center' }}>{value}</Text>
      <Pressable onPress={() => onChange(shiftDay(value, 1))} style={styles.stepBtn}>
        <Text style={{ color: colors.text, fontSize: 18 }}>+</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.45)',
    justifyContent: 'flex-end',
  },
  sheet: {
    borderTopLeftRadius: radii.lg,
    borderTopRightRadius: radii.lg,
    borderWidth: 1,
    padding: spacing.lg,
    gap: spacing.md,
    paddingBottom: spacing.xl,
  },
  title: { fontFamily: fonts.bodyMedium, fontSize: 17 },
  presets: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    borderWidth: 1,
    borderRadius: radii.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  section: { fontFamily: fonts.body, fontSize: 13 },
  stepper: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    gap: spacing.sm,
  },
  stepBtn: { width: 36, alignItems: 'center' },
  apply: {
    borderRadius: radii.md,
    paddingVertical: spacing.md,
    alignItems: 'center',
    marginTop: spacing.sm,
  },
});
