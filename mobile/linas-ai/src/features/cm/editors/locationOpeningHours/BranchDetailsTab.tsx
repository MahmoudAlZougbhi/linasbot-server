import { Linking, Pressable, Text, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../../../components/AppIcon';
import { useI18n } from '../../../../i18n/LanguageContext';
import { asRecord } from '../../cmApi';
import { Field } from '../Field';
import { branchAddress } from './branchScheduleHelpers';
import { hrefForOpen } from './branchMedia';
import { locStyles, locTeal } from './locationHoursStyles';
import { BranchMediaSection } from './BranchMediaSection';
import type { BranchAttachment } from './branchMedia';

type Props = {
  branch: Record<string, unknown>;
  onPatch: (data: Record<string, unknown>) => void;
};

export function BranchDetailsTab({ branch, onPatch }: Props) {
  const { tr } = useI18n();
  const mapsUrl = String(branch.maps_url || '');

  const openMap = () => {
    const href = hrefForOpen(mapsUrl);
    if (href) void Linking.openURL(href);
  };

  return (
    <View>
      <Field
        label={tr('aiSetupLocBranchName')}
        value={String(asRecord(branch.labels).en || '')}
        onChange={(v) => onPatch({ labels: { ...asRecord(branch.labels), en: v } })}
      />
      <Field
        label={tr('aiSetupLocAddress')}
        value={branchAddress(branch)}
        onChange={(v) =>
          onPatch({
            address: v,
            street: '',
            building: '',
            floor: '',
            country: '',
          })
        }
      />
      <Text style={locStyles.fieldLabel}>{tr('aiSetupLocMapLink')}</Text>
      <View style={locStyles.mapWrap}>
        <TextInput
          style={locStyles.mapInput}
          value={mapsUrl}
          onChangeText={(maps_url) => onPatch({ maps_url })}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder="maps.google.com/…"
          placeholderTextColor="#8A9A98"
        />
        <Pressable style={locStyles.mapBtn} onPress={openMap} disabled={!mapsUrl.trim()} accessibilityRole="link">
          <AppIcon icon={feather('external-link')} size={18} color={locTeal} />
        </Pressable>
      </View>
      <Field
        label={tr('aiSetupLocBranchNote')}
        value={String(branch.notes || '')}
        onChange={(notes) => onPatch({ notes: notes || null })}
        multiline
      />
      <BranchMediaSection
        mapsUrl={mapsUrl}
        attachments={branch.attachments}
        onMapsUrl={(url) => onPatch({ maps_url: url })}
        onAttachments={(next: BranchAttachment[]) => onPatch({ attachments: next })}
      />
    </View>
  );
}
