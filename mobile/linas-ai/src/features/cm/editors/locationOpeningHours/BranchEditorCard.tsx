import { useMemo } from 'react';
import { Text, View } from 'react-native';

import { PrimaryButton } from '../../../../components/PrimaryButton';
import { useI18n } from '../../../../i18n/LanguageContext';
import { asRecord } from '../../cmApi';
import { cmFormStyles } from '../../cmFormStyles';
import { Field } from '../Field';
import { BranchDayRow } from './BranchDayRow';
import { normalizeWeeklySchedule, patchWeeklyDay } from './branchScheduleHelpers';
import { WEEKDAY_KEYS } from './branchScheduleTypes';

type Props = {
  branch: Record<string, unknown>;
  onPatch: (data: Record<string, unknown>) => void;
  onDelete: () => void;
};

export function BranchEditorCard({ branch, onPatch, onDelete }: Props) {
  const { tr } = useI18n();
  const schedule = useMemo(
    () => normalizeWeeklySchedule(branch.weekly_schedule),
    [branch.weekly_schedule],
  );

  const patchDay = (dayKey: typeof WEEKDAY_KEYS[number], patch: Partial<typeof schedule.monday>) => {
    onPatch({ weekly_schedule: patchWeeklyDay(schedule, dayKey, patch) });
  };

  return (
    <View style={cmFormStyles.card}>
      <Field
        label={tr('aiSetupLocBranchName')}
        value={String(asRecord(branch.labels).en || '')}
        onChange={(v) =>
          onPatch({
            labels: { ...asRecord(branch.labels), en: v },
          })
        }
      />
      <Field
        label={tr('aiSetupLocMapLink')}
        value={String(branch.maps_url || '')}
        onChange={(maps_url) => onPatch({ maps_url })}
        placeholder="https://maps.google.com/…"
      />
      <Text style={[cmFormStyles.label, { marginTop: 12 }]}>{tr('aiSetupLocWeeklyHours')}</Text>
      {WEEKDAY_KEYS.map((dayKey) => (
        <BranchDayRow
          key={dayKey}
          dayKey={dayKey}
          day={schedule[dayKey]}
          onChange={(next) => patchDay(dayKey, next)}
        />
      ))}
      <View style={{ height: 12 }} />
      <PrimaryButton label={tr('aiSetupLocDeleteBranch')} variant="ghost" onPress={onDelete} />
    </View>
  );
}
