import { Pressable, Text, View } from 'react-native';

import { AppIcon, feather } from '../../../../components/AppIcon';
import { useI18n } from '../../../../i18n/LanguageContext';
import { primaryLabel } from '../../cmApi';
import {
  branchAddress,
  branchMediaCount,
  formatClock12,
  hoursAreSet,
  normalizeWeeklySchedule,
  todayStatus,
} from './branchScheduleHelpers';
import { locGreen, locOrange, locStyles } from './locationHoursStyles';

type Props = {
  branch: Record<string, unknown>;
  onPress: () => void;
};

export function BranchCard({ branch, onPress }: Props) {
  const { tr } = useI18n();
  const schedule = normalizeWeeklySchedule(branch.weekly_schedule);
  const hoursSet = hoursAreSet(schedule);
  const status = todayStatus(schedule);
  const mediaCount = branchMediaCount(branch);
  const name = primaryLabel(branch.labels) || tr('aiSetupLocUntitledBranch');
  const address = branchAddress(branch);
  const mediaLabel =
    mediaCount === 1
      ? tr('aiSetupLocMediaOne')
      : mediaCount > 1
        ? tr('aiSetupLocMediaMany').replace('{count}', String(mediaCount))
        : '';
  const footer =
    !hoursSet && mediaLabel
      ? `${tr('aiSetupLocNoHours')} · ${mediaLabel}`
      : !hoursSet
        ? tr('aiSetupLocNoHours')
        : mediaLabel;

  return (
    <Pressable style={locStyles.card} onPress={onPress} accessibilityRole="button">
      <View style={locStyles.pin}>
        <AppIcon icon={feather('map-pin')} size={18} color="#FFFFFF" />
      </View>
      <View style={locStyles.cardBody}>
        <Text style={locStyles.name} numberOfLines={1}>
          {name}
        </Text>
        {address ? (
          <Text style={locStyles.address} numberOfLines={1}>
            {address}
          </Text>
        ) : null}
        {status.kind === 'open' ? (
          <View style={locStyles.statusRow}>
            <View style={[locStyles.dot, { backgroundColor: locGreen }]} />
            <Text style={[locStyles.statusText, { color: locGreen }]}>
              {tr('aiSetupLocOpenToday').replace(
                '{hours}',
                `${formatClock12(status.open)}–${formatClock12(status.close)}`,
              )}
            </Text>
          </View>
        ) : null}
        {status.kind === 'closed' ? (
          <View style={locStyles.statusRow}>
            <View style={[locStyles.dot, { backgroundColor: locOrange }]} />
            <Text style={[locStyles.statusText, { color: locOrange }]}>{tr('aiSetupLocClosedToday')}</Text>
          </View>
        ) : null}
        {!hoursSet ? (
          <View style={locStyles.draftBadge}>
            <Text style={locStyles.draftText}>{tr('aiSetupLocDraft')}</Text>
          </View>
        ) : null}
        {footer ? (
          <View style={locStyles.mediaRow}>
            <AppIcon icon={feather('paperclip')} size={12} color="#8A9A98" />
            <Text style={locStyles.mediaText}>{footer}</Text>
          </View>
        ) : null}
      </View>
      <AppIcon icon={feather('chevron-right')} size={18} color="#8A9A98" />
    </Pressable>
  );
}
