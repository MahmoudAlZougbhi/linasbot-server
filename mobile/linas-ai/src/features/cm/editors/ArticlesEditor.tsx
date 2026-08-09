import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { PrimaryButton } from '../../../components/PrimaryButton';
import { asRecordList, newId } from '../cmApi';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';

type Props = {
  section: 'knowledge' | 'care';
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

export function ArticlesEditor({ section, payload, onChange }: Props) {
  const items = asRecordList(payload.items);
  const [selectedId, setSelectedId] = useState<string | null>(
    items[0] ? String(items[0].id) : null,
  );
  const selected = items.find((item) => String(item.id) === selectedId) || items[0] || null;

  const setItems = (next: Record<string, unknown>[]) => onChange({ ...payload, items: next });

  const add = () => {
    const id = newId(section);
    setItems([
      {
        id,
        title: '',
        body: '',
        tags: [],
        language: '',
        audience: 'general',
        category: '',
        status: 'active',
        source_filename: null,
        source_checksum: null,
        linked_service_ids: [],
        linked_branch_ids: [],
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
      <PrimaryButton label="Add article" onPress={add} variant="ghost" />
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
            <Text style={cmFormStyles.itemTitle}>{String(item.title || id)}</Text>
          </Pressable>
        );
      })}
      {selected ? (
        <View style={cmFormStyles.card}>
          <Field
            label="Title"
            value={String(selected.title || '')}
            onChange={(v) => patch(String(selected.id), { title: v })}
          />
          <Field
            label="Note"
            value={String(selected.body || '')}
            onChange={(v) => patch(String(selected.id), { body: v })}
            multiline
            hint="Stored as article body in the CM draft."
          />
        </View>
      ) : (
        <Text style={cmFormStyles.hint}>No articles yet.</Text>
      )}
    </View>
  );
}
