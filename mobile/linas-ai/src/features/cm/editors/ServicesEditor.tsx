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
        labels: emptyLabels(),
        available: true,
        category: '',
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
      <Text style={cmFormStyles.hint}>{items.length} services in draft catalog.</Text>
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
              {item.available === false ? 'Unavailable' : 'Available'}
            </Text>
          </Pressable>
        );
      })}
      {selected ? (
        <View style={cmFormStyles.card}>
          {(['en', 'ar', 'fr', 'franco'] as const).map((lang) => (
            <Field
              key={lang}
              label={`Name (${lang})`}
              value={String(asRecord(selected.labels)[lang] || '')}
              onChange={(v) =>
                patch(String(selected.id), {
                  labels: { ...emptyLabels(), ...asRecord(selected.labels), [lang]: v },
                })
              }
            />
          ))}
          <Field
            label="Category"
            value={String(selected.category || '')}
            onChange={(v) => patch(String(selected.id), { category: v })}
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
          <Field
            label="Notes"
            value={String(selected.notes || '')}
            onChange={(v) => patch(String(selected.id), { notes: v })}
            multiline
          />
        </View>
      ) : (
        <Text style={cmFormStyles.hint}>No services yet — tap Add service.</Text>
      )}
    </View>
  );
}
