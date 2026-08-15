import { useMemo, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { PrimaryButton } from '../../../components/PrimaryButton';
import { useI18n } from '../../../i18n/LanguageContext';
import { asRecordList, newId, primaryLabel } from '../cmApi';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';
import { BranchEditorCard } from './locationOpeningHours/BranchEditorCard';
import { newBranchRecord } from './locationOpeningHours/branchScheduleHelpers';
import { SpecificOffDaysCalendar } from './locationOpeningHours/SpecificOffDaysCalendar';

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

export function LocationOpeningHoursEditor({ payload, onChange }: Props) {
  const { tr } = useI18n();
  const items = asRecordList(payload.items);
  const [selectedId, setSelectedId] = useState<string | null>(
    items[0] ? String(items[0].id) : null,
  );
  const selected = items.find((i) => String(i.id) === selectedId) || items[0] || null;
  const setItems = (next: Record<string, unknown>[]) => onChange({ ...payload, items: next });

  const patchBranch = (id: string, data: Record<string, unknown>) => {
    setItems(items.map((i) => (String(i.id) === id ? { ...i, ...data } : i)));
  };

  const specificRules = useMemo(
    () => asRecordList(payload.specific_off_rules),
    [payload.specific_off_rules],
  );

  return (
    <View>
      <Text style={cmFormStyles.hint}>{tr('aiSetupLocHint')}</Text>
      <PrimaryButton
        label={tr('aiSetupLocAddBranch')}
        variant="ghost"
        onPress={() => {
          const id = newId('branch');
          setItems([newBranchRecord(id), ...items]);
          setSelectedId(id);
        }}
      />
      <View style={{ height: 12 }} />
      {items.map((item) => (
        <Pressable
          key={String(item.id)}
          style={cmFormStyles.itemCard}
          onPress={() => setSelectedId(String(item.id))}
        >
          <Text style={cmFormStyles.itemTitle}>
            {primaryLabel(item.labels) || tr('aiSetupLocUntitledBranch')}
          </Text>
          <Text style={cmFormStyles.itemSub}>{String(item.maps_url || '')}</Text>
        </Pressable>
      ))}
      {selected ? (
        <BranchEditorCard
          branch={selected}
          onPatch={(data) => patchBranch(String(selected.id), data)}
          onDelete={() => {
            const next = items.filter((i) => String(i.id) !== String(selected.id));
            setItems(next);
            setSelectedId(next[0] ? String(next[0].id) : null);
          }}
        />
      ) : (
        <Text style={cmFormStyles.hint}>{tr('aiSetupLocEmpty')}</Text>
      )}
      <View style={{ height: 16 }} />
      <SpecificOffDaysCalendar
        rules={specificRules}
        onChange={(rules) => onChange({ ...payload, specific_off_rules: rules })}
      />
      <Field
        label={tr('aiSetupLocPolicy')}
        value={String(payload.policy_text || '')}
        onChange={(v) => onChange({ ...payload, policy_text: v })}
        multiline
      />
    </View>
  );
}
