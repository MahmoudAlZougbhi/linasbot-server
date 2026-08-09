import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { PrimaryButton } from '../../../components/PrimaryButton';
import { asRecordList, newId } from '../cmApi';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

export function PricesEditor({ payload, onChange }: Props) {
  const items = asRecordList(payload.items);
  const catalog = asRecordList(payload.catalog);
  const priceEntries = asRecordList(payload.price_entries);
  const [selectedId, setSelectedId] = useState<string | null>(
    items[0] ? String(items[0].id) : null,
  );
  const selected = items.find((item) => String(item.id) === selectedId) || items[0] || null;

  const setItems = (next: Record<string, unknown>[]) => onChange({ ...payload, items: next });

  const add = () => {
    const id = newId('price');
    setItems([
      { id, service_id: '', amount: 0, currency: 'USD', unit: null, branch_id: null, notes: null },
      ...items,
    ]);
    setSelectedId(id);
  };

  const patch = (id: string, patchData: Record<string, unknown>) =>
    setItems(items.map((item) => (String(item.id) === id ? { ...item, ...patchData } : item)));

  return (
    <View>
      <Text style={cmFormStyles.hint}>
        Catalog: {catalog.length} · Price entries: {priceEntries.length} · Legacy rows: {items.length}.
        Full matrix / discounts wizard stays on the web dashboard.
      </Text>
      <View style={cmFormStyles.card}>
        <Field
          label="Pricing policy text"
          value={String(payload.policy_text || '')}
          onChange={(v) => onChange({ ...payload, policy_text: v })}
          multiline
        />
        <Field
          label="Notes"
          value={String(payload.notes || '')}
          onChange={(v) => onChange({ ...payload, notes: v })}
          multiline
        />
      </View>
      <PrimaryButton label="Add legacy price row" onPress={add} variant="ghost" />
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
            <Text style={cmFormStyles.itemTitle}>
              {String(item.service_id || id)} — {String(item.amount ?? 0)}{' '}
              {String(item.currency || 'USD')}
            </Text>
          </Pressable>
        );
      })}
      {selected ? (
        <View style={cmFormStyles.card}>
          <Field
            label="Service ID"
            value={String(selected.service_id || '')}
            onChange={(v) => patch(String(selected.id), { service_id: v })}
          />
          <Field
            label="Amount"
            value={String(selected.amount ?? '')}
            onChange={(v) => {
              const n = Number(v);
              patch(String(selected.id), { amount: Number.isFinite(n) ? n : 0 });
            }}
          />
          <Field
            label="Currency"
            value={String(selected.currency || 'USD')}
            onChange={(v) => patch(String(selected.id), { currency: v })}
          />
          <Field
            label="Unit"
            value={String(selected.unit || '')}
            onChange={(v) => patch(String(selected.id), { unit: v || null })}
          />
          <Field
            label="Notes"
            value={String(selected.notes || '')}
            onChange={(v) => patch(String(selected.id), { notes: v })}
            multiline
          />
        </View>
      ) : null}
    </View>
  );
}
