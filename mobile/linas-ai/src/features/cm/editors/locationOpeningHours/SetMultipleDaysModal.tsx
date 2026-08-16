import { useState } from 'react';
import { Pressable, ScrollView, Switch, Text, View } from 'react-native';

import { AppModal } from '../../../../components/AppModal';
import { ModalScrim } from '../../../../components/ModalScrim';
import { useI18n } from '../../../../i18n/LanguageContext';
import type { StringKey } from '../../../../i18n/locales/en';
import type { WeekdayKey } from './branchScheduleTypes';
import { WEEKDAY_KEYS } from './branchScheduleTypes';
import { DEFAULT_CLOSE, DEFAULT_OPEN, dayOffPatch, openDayPatch } from './branchScheduleHelpers';
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
  visible: boolean;
  onClose: () => void;
  onApply: (days: WeekdayKey[], patch: ReturnType<typeof openDayPatch>) => void;
};

export function SetMultipleDaysModal({ visible, onClose, onApply }: Props) {
  const { tr } = useI18n();
  const [selected, setSelected] = useState<WeekdayKey[]>([...WEEKDAY_KEYS]);
  const [off, setOff] = useState(false);
  const [open, setOpen] = useState(DEFAULT_OPEN);
  const [close, setClose] = useState(DEFAULT_CLOSE);

  const toggle = (day: WeekdayKey) => {
    setSelected((prev) => (prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day]));
  };

  return (
    <AppModal visible={visible} onRequestClose={onClose}>
      <ModalScrim onPress={onClose}>
        <Pressable style={locStyles.sheet} onPress={(e) => e.stopPropagation()}>
          <Text style={locStyles.sheetTitle}>{tr('aiSetupLocSetMultiple')}</Text>
          <Text style={locStyles.sectionHint}>{tr('aiSetupLocSameHoursBody')}</Text>
          <ScrollView>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
              {WEEKDAY_KEYS.map((day) => {
                const on = selected.includes(day);
                return (
                  <Pressable
                    key={day}
                    style={[locStyles.dayChip, on && locStyles.dayChipOn]}
                    onPress={() => toggle(day)}
                  >
                    <Text style={on ? locStyles.sameHoursTitle : locStyles.mediaKind}>{tr(WEEKDAY_I18N[day])}</Text>
                  </Pressable>
                );
              })}
            </View>
            <View style={[locStyles.dayRow, { marginTop: 8, borderBottomWidth: 0 }]}>
              <Text style={locStyles.dayOffLabel}>{tr('aiSetupLocDayOff')}</Text>
              <Switch
                value={off}
                onValueChange={setOff}
                trackColor={{ false: '#E5E7EB', true: '#FDBA74' }}
                thumbColor={off ? locOrange : '#F9FAFB'}
              />
            </View>
            {off ? null : (
              <View style={[locStyles.dayRow, { borderBottomWidth: 0 }]}>
                <TimeField value={open} onChange={setOpen} />
                <Text style={locStyles.dash}>–</Text>
                <TimeField value={close} onChange={setClose} />
              </View>
            )}
          </ScrollView>
          <View style={locStyles.footer}>
            <Pressable style={locStyles.outlineBtn} onPress={onClose}>
              <Text style={locStyles.outlineBtnText}>{tr('aiSetupLocCancel')}</Text>
            </Pressable>
            <Pressable
              style={locStyles.saveBtn}
              onPress={() => {
                if (!selected.length) return;
                onApply(selected, off ? dayOffPatch() : openDayPatch(open || DEFAULT_OPEN, close || DEFAULT_CLOSE));
                onClose();
              }}
            >
              <Text style={locStyles.saveText}>{tr('aiSetupLocApply')}</Text>
            </Pressable>
          </View>
        </Pressable>
      </ModalScrim>
    </AppModal>
  );
}
