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

function composeAddress(parts: {
  street?: string;
  building?: string;
  floor?: string;
  country?: string;
}): string {
  return [parts.street, parts.building, parts.floor, parts.country]
    .map((p) => (p || '').trim())
    .filter(Boolean)
    .join(', ');
}

export function BranchesEditor({ payload, onChange }: Props) {
  const items = asRecordList(payload.items);
  const [selectedId, setSelectedId] = useState<string | null>(
    items[0] ? String(items[0].id) : null,
  );
  const selected = items.find((i) => String(i.id) === selectedId) || items[0] || null;
  const setItems = (next: Record<string, unknown>[]) => onChange({ ...payload, items: next });

  const patch = (id: string, data: Record<string, unknown>) => {
    setItems(
      items.map((i) => {
        if (String(i.id) !== id) return i;
        const next = { ...i, ...data };
        const street = String(next.street || '');
        const building = String(next.building || '');
        const floor = String(next.floor || '');
        const country = String(next.country || '');
        next.address = composeAddress({ street, building, floor, country }) || String(next.address || '');
        return next;
      }),
    );
  };

  return (
    <View>
      <PrimaryButton
        label="Add Location"
        variant="ghost"
        onPress={() => {
          const id = newId('branch');
          setItems([
            {
              id,
              labels: emptyLabels(),
              address: '',
              street: '',
              building: '',
              floor: '',
              country: '',
              maps_url: '',
              hours: {},
              available: true,
              notes: null,
            },
            ...items,
          ]);
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
          <Text style={cmFormStyles.itemTitle}>{primaryLabel(item.labels) || String(item.id)}</Text>
          <Text style={cmFormStyles.itemSub}>
            {String(item.address || composeAddress(item as { street?: string }))}
          </Text>
        </Pressable>
      ))}
      {selected ? (
        <View style={cmFormStyles.card}>
          <Field
            label="Branch name"
            value={String(asRecord(selected.labels).en || '')}
            onChange={(v) =>
              patch(String(selected.id), {
                labels: { ...emptyLabels(), ...asRecord(selected.labels), en: v },
              })
            }
          />
          <Field
            label="Street"
            value={String(selected.street || '')}
            onChange={(v) => patch(String(selected.id), { street: v })}
          />
          <Field
            label="Building"
            value={String(selected.building || '')}
            onChange={(v) => patch(String(selected.id), { building: v })}
          />
          <Field
            label="Floor"
            value={String(selected.floor || '')}
            onChange={(v) => patch(String(selected.id), { floor: v })}
          />
          <Field
            label="Country"
            value={String(selected.country || '')}
            onChange={(v) => patch(String(selected.id), { country: v })}
          />
          <Field
            label="Google Maps link"
            value={String(selected.maps_url || '')}
            onChange={(v) => patch(String(selected.id), { maps_url: v })}
            placeholder="https://maps.google.com/…"
          />
        </View>
      ) : (
        <Text style={cmFormStyles.hint}>No locations yet — tap Add Location.</Text>
      )}
    </View>
  );
}
