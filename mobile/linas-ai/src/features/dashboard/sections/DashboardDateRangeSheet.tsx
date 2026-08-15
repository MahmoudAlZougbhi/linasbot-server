import { useEffect, useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../../i18n/LanguageContext';
import type { StringKey } from '../../../i18n';
import { fonts, radii, spacing, useTheme } from '../../../theme';
import { RequestMonthCalendar } from '../../requests/RequestDatePicker';
import type { DashboardPeriodSelection, DashboardPresetId } from '../dashboardFormat';
import { todayIso } from '../dashboardFormat';

type Props = {
  open: boolean;
  period: DashboardPeriodSelection;
  onClose: () => void;
  onApply: (next: DashboardPeriodSelection) => void;
};

type Preset = {
  id: DashboardPresetId;
  labelKey: 'dashToday' | 'dashLastMonth' | 'dashLast6Months' | 'dashLastYear';
};

const PRESETS: Preset[] = [
  { id: 'today', labelKey: 'dashToday' },
  { id: 'last_month', labelKey: 'dashLastMonth' },
  { id: 'last_6m', labelKey: 'dashLast6Months' },
  { id: 'last_year', labelKey: 'dashLastYear' },
];

export function DashboardDateRangeSheet({ open, period, onClose, onApply }: Props) {
  const { colors } = useTheme();
  const { tr, language } = useI18n();
  const locale = language === 'ar' ? 'ar' : language === 'fr' ? 'fr' : 'en-US';
  const [calPhase, setCalPhase] = useState<null | 'start' | 'end'>(null);
  const [draftStart, setDraftStart] = useState(todayIso());

  useEffect(() => {
    if (!open) {
      setCalPhase(null);
      return;
    }
    if (period.kind === 'custom') setDraftStart(period.start);
    else setDraftStart(todayIso());
  }, [open, period]);

  const titleKey: StringKey = calPhase === 'end' ? 'dashRangeEnd' : calPhase === 'start' ? 'dashRangeStart' : 'dashSelectRange';

  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable
          style={[styles.sheet, { backgroundColor: colors.surface, borderColor: colors.border }]}
          onPress={(e) => e.stopPropagation()}
        >
          <Text style={[styles.title, { color: colors.text }]}>{tr(titleKey)}</Text>

          {calPhase ? (
            <RequestMonthCalendar
              locale={locale}
              value={draftStart}
              onPick={(ymd) => {
                if (calPhase === 'start') {
                  setDraftStart(ymd);
                  setCalPhase('end');
                  return;
                }
                const start = draftStart;
                const [from, to] = start <= ymd ? [start, ymd] : [ymd, start];
                onApply({ kind: 'custom', start: from, end: to });
              }}
            />
          ) : (
            <View style={styles.presets}>
              {PRESETS.map((preset) => {
                const active = period.kind === 'preset' && period.id === preset.id;
                return (
                  <Pressable
                    key={preset.id}
                    onPress={() => onApply({ kind: 'preset', id: preset.id })}
                    accessibilityRole="button"
                    accessibilityLabel={tr(preset.labelKey)}
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
              <Pressable
                onPress={() => setCalPhase('start')}
                accessibilityRole="button"
                accessibilityLabel={tr('dashCustom')}
                style={[
                  styles.chip,
                  {
                    backgroundColor: period.kind === 'custom' ? colors.accentSoft : colors.surfaceAlt,
                    borderColor: period.kind === 'custom' ? colors.accent : colors.border,
                  },
                ]}
              >
                <Text
                  style={{
                    color: period.kind === 'custom' ? colors.accentDeep : colors.text,
                    fontFamily: fonts.bodyMedium,
                  }}
                >
                  {tr('dashCustom')}
                </Text>
              </Pressable>
            </View>
          )}
        </Pressable>
      </Pressable>
    </Modal>
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
});
