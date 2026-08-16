import { useState } from 'react';
import { Pressable, Switch, Text, View } from 'react-native';

import { AppIcon, feather } from '../../../../components/AppIcon';
import { AppModal } from '../../../../components/AppModal';
import { ModalScrim } from '../../../../components/ModalScrim';
import { useI18n } from '../../../../i18n/LanguageContext';
import type { StringKey } from '../../../../i18n/locales/en';
import type { BranchDaySchedule, WeekdayKey } from './branchScheduleTypes';
import { dayOffPatch, DEFAULT_CLOSE, DEFAULT_OPEN, openDayPatch } from './branchScheduleHelpers';
import { locOrange, locStyles } from './locationHoursStyles';
import { TimeField } from './TimeField';

const WEEKDAY_I18N: Record<WeekdayKey, StringKey> = {
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
  last?: boolean;
};

export function BranchDayRow({ dayKey, day, onChange, last }: Props) {
  const { tr } = useI18n();
  const [menu, setMenu] = useState(false);
  const isOff = day.enabled && day.off_day;

  return (
    <View style={[locStyles.dayRow, last && { borderBottomWidth: 0 }]}>
      <Text style={locStyles.dayName}>{tr(WEEKDAY_I18N[dayKey])}</Text>
      {isOff ? (
        <>
          <Text style={locStyles.dayOffLabel}>{tr('aiSetupLocDayOff')}</Text>
          <Switch
            value
            onValueChange={(on) => {
              if (on) return;
              onChange(openDayPatch(day.open || DEFAULT_OPEN, day.close || DEFAULT_CLOSE));
            }}
            trackColor={{ false: '#E5E7EB', true: '#FDBA74' }}
            thumbColor={locOrange}
          />
        </>
      ) : (
        <>
          <TimeField
            value={day.open}
            onChange={(open) => onChange({ ...openDayPatch(open || DEFAULT_OPEN, day.close || DEFAULT_CLOSE), open })}
          />
          <Text style={locStyles.dash}>–</Text>
          <TimeField
            value={day.close}
            onChange={(close) =>
              onChange({ ...openDayPatch(day.open || DEFAULT_OPEN, close || DEFAULT_CLOSE), close })
            }
          />
          <Pressable style={locStyles.openBtn} onPress={() => setMenu(true)} accessibilityRole="button">
            <Text style={locStyles.openText}>{tr('aiSetupLocOpen')}</Text>
            <AppIcon icon={feather('chevron-down')} size={14} color="#15803D" />
          </Pressable>
        </>
      )}
      <AppModal visible={menu} onRequestClose={() => setMenu(false)}>
        <ModalScrim onPress={() => setMenu(false)}>
          <Pressable style={locStyles.sheet} onPress={(e) => e.stopPropagation()}>
            <Text style={locStyles.sheetTitle}>{tr(WEEKDAY_I18N[dayKey])}</Text>
            <Pressable
              style={locStyles.dayRow}
              onPress={() => {
                onChange(openDayPatch(day.open || DEFAULT_OPEN, day.close || DEFAULT_CLOSE));
                setMenu(false);
              }}
            >
              <Text style={locStyles.openText}>{tr('aiSetupLocOpen')}</Text>
            </Pressable>
            <Pressable
              style={[locStyles.dayRow, { borderBottomWidth: 0 }]}
              onPress={() => {
                onChange(dayOffPatch());
                setMenu(false);
              }}
            >
              <Text style={locStyles.dayOffLabel}>{tr('aiSetupLocDayOff')}</Text>
            </Pressable>
          </Pressable>
        </ModalScrim>
      </AppModal>
    </View>
  );
}
