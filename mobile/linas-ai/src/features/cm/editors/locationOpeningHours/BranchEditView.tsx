import { Pressable, ScrollView, Text, View } from 'react-native';

import { AppIcon, feather } from '../../../../components/AppIcon';
import { useI18n } from '../../../../i18n/LanguageContext';
import { hoursAreSet, normalizeWeeklySchedule } from './branchScheduleHelpers';
import { locGreen, locStyles, locTeal } from './locationHoursStyles';
import { BranchDetailsTab } from './BranchDetailsTab';
import { BranchHoursTab } from './BranchHoursTab';

type Tab = 'details' | 'hours';

type Props = {
  branch: Record<string, unknown>;
  tab: Tab;
  onTab: (tab: Tab) => void;
  onPatch: (data: Record<string, unknown>) => void;
  onSave: () => void;
  onDelete: () => void;
  saving?: boolean;
  canSave?: boolean;
};

export function BranchEditView({
  branch,
  tab,
  onTab,
  onPatch,
  onSave,
  onDelete,
  saving,
  canSave,
}: Props) {
  const { tr } = useI18n();
  const published = hoursAreSet(normalizeWeeklySchedule(branch.weekly_schedule));

  return (
    <ScrollView contentContainerStyle={{ paddingBottom: 48 }} keyboardShouldPersistTaps="handled">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <Text style={[locStyles.name, { color: locTeal }]}>{tr('aiSetupLocEditTitle')}</Text>
        {published ? (
          <View style={locStyles.published}>
            <View style={[locStyles.dot, { backgroundColor: locGreen }]} />
            <Text style={locStyles.publishedText}>{tr('aiSetupLocPublished')}</Text>
          </View>
        ) : (
          <View style={locStyles.draftBadge}>
            <Text style={locStyles.draftText}>{tr('aiSetupLocDraft')}</Text>
          </View>
        )}
      </View>
      <View style={locStyles.tabs}>
        <Pressable style={[locStyles.tab, tab === 'details' && locStyles.tabOn]} onPress={() => onTab('details')}>
          <Text style={[locStyles.tabText, tab === 'details' && locStyles.tabTextOn]}>
            {tr('aiSetupLocTabDetails')}
          </Text>
        </Pressable>
        <Pressable style={[locStyles.tab, tab === 'hours' && locStyles.tabOn]} onPress={() => onTab('hours')}>
          <Text style={[locStyles.tabText, tab === 'hours' && locStyles.tabTextOn]}>{tr('aiSetupLocTabHours')}</Text>
        </Pressable>
      </View>
      {tab === 'details' ? (
        <>
          <BranchDetailsTab branch={branch} onPatch={onPatch} />
          <View style={locStyles.footer}>
            <Pressable style={locStyles.deleteBtn} onPress={onDelete} accessibilityRole="button">
              <AppIcon icon={feather('trash-2')} size={16} color="#DC2626" />
              <Text style={locStyles.deleteText}>{tr('aiSetupLocDeleteBranch')}</Text>
            </Pressable>
            <Pressable
              style={[locStyles.saveBtn, (!canSave || saving) && { opacity: 0.5 }]}
              onPress={onSave}
              disabled={!canSave || saving}
            >
              <Text style={locStyles.saveText}>{tr('aiSetupLocSaveChanges')}</Text>
            </Pressable>
          </View>
        </>
      ) : (
        <BranchHoursTab branch={branch} onPatch={onPatch} onSave={onSave} saving={saving} canSave={canSave} />
      )}
    </ScrollView>
  );
}
