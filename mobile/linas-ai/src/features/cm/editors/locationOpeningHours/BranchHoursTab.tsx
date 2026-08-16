import { useMemo, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { AppIcon, feather } from '../../../../components/AppIcon';
import { useI18n } from '../../../../i18n/LanguageContext';
import { WEEKDAY_KEYS } from './branchScheduleTypes';
import { applyScheduleToDays, normalizeWeeklySchedule } from './branchScheduleHelpers';
import { locStyles, locTeal } from './locationHoursStyles';
import { BranchDayRow } from './BranchDayRow';
import { SetMultipleDaysModal } from './SetMultipleDaysModal';

type Props = {
  branch: Record<string, unknown>;
  onPatch: (data: Record<string, unknown>) => void;
  onSave: () => void;
  saving?: boolean;
  canSave?: boolean;
};

export function BranchHoursTab({ branch, onPatch, onSave, saving, canSave }: Props) {
  const { tr } = useI18n();
  const [bulk, setBulk] = useState(false);
  const schedule = useMemo(
    () => normalizeWeeklySchedule(branch.weekly_schedule),
    [branch.weekly_schedule],
  );

  return (
    <View>
      <Text style={locStyles.sectionTitle}>{tr('aiSetupLocWeeklyHours')}</Text>
      <Text style={locStyles.sectionHint}>{tr('aiSetupLocWeeklyHint')}</Text>
      <View style={locStyles.sameHours}>
        <AppIcon icon={feather('clock')} size={18} color={locTeal} />
        <View style={{ flex: 1 }}>
          <Text style={locStyles.sameHoursTitle}>{tr('aiSetupLocSameHoursTitle')}</Text>
          <Text style={locStyles.sameHoursBody}>{tr('aiSetupLocSameHoursBody')}</Text>
        </View>
        <Pressable style={locStyles.outlineBtn} onPress={() => setBulk(true)}>
          <Text style={locStyles.outlineBtnText}>{tr('aiSetupLocSetMultiple')}</Text>
        </Pressable>
      </View>
      <View style={locStyles.weekBox}>
        {WEEKDAY_KEYS.map((dayKey, index) => (
          <BranchDayRow
            key={dayKey}
            dayKey={dayKey}
            day={schedule[dayKey]}
            last={index === WEEKDAY_KEYS.length - 1}
            onChange={(next) => onPatch({ weekly_schedule: { ...schedule, [dayKey]: next } })}
          />
        ))}
      </View>
      <Text style={locStyles.help}>{tr('aiSetupLocDayOffHelp')}</Text>
      <Pressable
        style={[locStyles.saveBtn, (!canSave || saving) && { opacity: 0.5 }]}
        onPress={onSave}
        disabled={!canSave || saving}
      >
        <Text style={locStyles.saveText}>{tr('aiSetupLocSaveHours')}</Text>
      </Pressable>
      <SetMultipleDaysModal
        visible={bulk}
        onClose={() => setBulk(false)}
        onApply={(days, patch) => onPatch({ weekly_schedule: applyScheduleToDays(schedule, days, patch) })}
      />
    </View>
  );
}
