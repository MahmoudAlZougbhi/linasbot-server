import { useState } from 'react';
import { Pressable, Switch, Text, View } from 'react-native';

import { useI18n } from '../../../../i18n/LanguageContext';
import { cmFormStyles } from '../../cmFormStyles';
import { Field } from '../Field';
import type { BranchDaySchedule, WeekdayKey } from './branchScheduleTypes';

const WEEKDAY_I18N: Record<WeekdayKey, string> = {
  monday: 'aiSetupLocDay_monday',
  tuesday: 'aiSetupLocDay_tuesday',
  wednesday: 'aiSetupLocDay_wednesday',
  thursday: 'aiSetupLocDay_thursday',
  friday: 'aiSetupLocDay_friday',
  saturday: 'aiSetupLocDay_saturday',
  sunday: 'aiSetupLocDay_sunday',
};

type Props = {
  dayKey: WeekdayKey;
  day: BranchDaySchedule;
  onChange: (next: BranchDaySchedule) => void;
};

export function BranchDayRow({ dayKey, day, onChange }: Props) {
  const { tr } = useI18n();
  const [noteOpen, setNoteOpen] = useState(Boolean(day.note && day.note.trim()));

  return (
    <View style={{ marginTop: 10, paddingTop: 8, borderTopWidth: 1, borderTopColor: '#E8E8E8' }}>
      <View style={cmFormStyles.row}>
        <Text style={cmFormStyles.rowTitle}>{tr(WEEKDAY_I18N[dayKey] as never)}</Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Text style={cmFormStyles.hint}>{tr('aiSetupLocDayEnabled')}</Text>
          <Switch value={day.enabled} onValueChange={(enabled) => onChange({ ...day, enabled })} />
        </View>
      </View>
      {day.enabled ? (
        <>
          <View style={[cmFormStyles.row, { marginTop: 6 }]}>
            <Text style={cmFormStyles.hint}>{tr('aiSetupLocDayOff')}</Text>
            <Switch
              value={day.off_day}
              onValueChange={(off_day) =>
                onChange({
                  ...day,
                  off_day,
                  ...(off_day ? { open: '', close: '' } : {}),
                })
              }
            />
          </View>
          {!day.off_day ? (
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 6 }}>
              <View style={{ flex: 1 }}>
                <Field
                  label={tr('aiSetupLocFrom')}
                  value={day.open}
                  onChange={(open) => onChange({ ...day, open })}
                  placeholder="09:00"
                />
              </View>
              <View style={{ flex: 1 }}>
                <Field
                  label={tr('aiSetupLocTo')}
                  value={day.close}
                  onChange={(close) => onChange({ ...day, close })}
                  placeholder="18:00"
                />
              </View>
            </View>
          ) : null}
          <Pressable style={{ marginTop: 8 }} onPress={() => setNoteOpen((v) => !v)}>
            <Text style={cmFormStyles.chipText}>
              {noteOpen ? tr('aiSetupLocHideDayNote') : tr('aiSetupLocAddDayNote')}
            </Text>
          </Pressable>
          {noteOpen ? (
            <Field
              label={tr('aiSetupLocDayNote')}
              value={day.note || ''}
              onChange={(note) => onChange({ ...day, note: note || null })}
              multiline
            />
          ) : null}
        </>
      ) : null}
    </View>
  );
}
