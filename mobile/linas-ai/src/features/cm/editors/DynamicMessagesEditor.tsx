import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { PrimaryButton } from '../../../components/PrimaryButton';
import { asRecordList, newId } from '../cmApi';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';

type EditorProps = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

export function DynamicMessagesEditor({ payload, onChange }: EditorProps) {
  const items = asRecordList(payload.items);
  const [selectedId, setSelectedId] = useState<string | null>(
    items[0] ? String(items[0].id) : null,
  );
  const selected = items.find((i) => String(i.id) === selectedId) || items[0] || null;
  const setItems = (next: Record<string, unknown>[]) => onChange({ ...payload, items: next });
  const patch = (id: string, data: Record<string, unknown>) =>
    setItems(items.map((i) => (String(i.id) === id ? { ...i, ...data } : i)));

  return (
    <View>
      <Text style={cmFormStyles.hint}>
        Greeting and message entries. English name + English note only (stored as name + en).
      </Text>
      <PrimaryButton
        label="Add message"
        variant="ghost"
        onPress={() => {
          const id = newId('msg');
          setItems([{ id, name: '', ar: '', en: '', fr: '', notes: null }, ...items]);
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
          <Text style={cmFormStyles.itemTitle}>{String(item.name || item.id)}</Text>
        </Pressable>
      ))}
      {selected ? (
        <View style={cmFormStyles.card}>
          <Field
            label="Name (English)"
            value={String(selected.name || '')}
            onChange={(v) => patch(String(selected.id), { name: v })}
          />
          <Field
            label="Note (English)"
            value={String(selected.en || selected.notes || '')}
            onChange={(v) =>
              patch(String(selected.id), { en: v, notes: v || null })
            }
            multiline
            hint="Message text / when it is used. Saved to the English message field."
          />
        </View>
      ) : null}
    </View>
  );
}
