import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { PrimaryButton } from '../../../components/PrimaryButton';
import { asRecord, asRecordList, emptyLabels, newId, primaryLabel } from '../cmApi';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

export function ServicesEditor({ payload, onChange }: Props) {
  const items = asRecordList(payload.items);
  const [selectedId, setSelectedId] = useState<string | null>(
    items[0] ? String(items[0].id) : null,
  );
  const selected = items.find((item) => String(item.id) === selectedId) || items[0] || null;

  const setItems = (next: Record<string, unknown>[]) => onChange({ ...payload, items: next });

  const add = () => {
    const id = newId('service');
    setItems([
      {
        id,
        labels: { ...emptyLabels(), en: '' },
        available: true,
        category: null,
        aliases: [],
        audience: 'general',
        notes: null,
      },
      ...items,
    ]);
    setSelectedId(id);
  };

  const patch = (id: string, patchData: Record<string, unknown>) =>
    setItems(items.map((item) => (String(item.id) === id ? { ...item, ...patchData } : item)));

  return (
    <View>
      <PrimaryButton label="Add service" onPress={add} variant="ghost" />
      <View style={{ height: 12 }} />
      {items.map((item) => {
        const id = String(item.id);
        const active = selected && String(selected.id) === id;
        return (
          <Pressable
            key={id}
            style={[cmFormStyles.itemCard, active && { borderColor: '#2563EB' }]}
            onPress={() => setSelectedId(id)}
          >
            <Text style={cmFormStyles.itemTitle}>{primaryLabel(item.labels) || id}</Text>
            <Text style={cmFormStyles.itemSub}>
              {item.available === false ? 'Off' : 'Available'}
            </Text>
          </Pressable>
        );
      })}
      {selected ? (
        <View style={cmFormStyles.card}>
          <Field
            label="Name"
            value={String(asRecord(selected.labels).en || '')}
            onChange={(v) =>
              patch(String(selected.id), {
                labels: { ...emptyLabels(), ...asRecord(selected.labels), en: v },
              })
            }
          />
          <Field
            label="Note"
            value={String(selected.notes || '')}
            onChange={(v) => patch(String(selected.id), { notes: v || null })}
            multiline
          />
          <Pressable
            style={cmFormStyles.row}
            onPress={() =>
              patch(String(selected.id), { available: selected.available === false })
            }
          >
            <Text style={cmFormStyles.rowTitle}>Available</Text>
            <Text style={cmFormStyles.chipText}>
              {selected.available === false ? 'Off' : 'On'}
            </Text>
          </Pressable>
        </View>
      ) : (
        <Text style={cmFormStyles.hint}>No services yet — tap Add service.</Text>
      )}
    </View>
  );
}
