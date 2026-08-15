import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { PrimaryButton } from '../../../components/PrimaryButton';
import { asRecord, asRecordList, emptyLabels, listToText, newId, primaryLabel, textToList } from '../cmApi';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';

type EditorProps = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

export function RestrictedEditor({ payload, onChange }: EditorProps) {
  const topics = asRecordList(payload.topics);
  const [selectedId, setSelectedId] = useState<string | null>(
    topics[0] ? String(topics[0].id) : null,
  );
  const selected = topics.find((t) => String(t.id) === selectedId) || topics[0] || null;
  const setTopics = (next: Record<string, unknown>[]) => onChange({ ...payload, topics: next });
  const patch = (id: string, data: Record<string, unknown>) =>
    setTopics(topics.map((t) => (String(t.id) === id ? { ...t, ...data } : t)));

  return (
    <View>
      <PrimaryButton
        label="Add restricted topic"
        variant="ghost"
        onPress={() => {
          const id = newId('restricted');
          setTopics([
            {
              id,
              labels: emptyLabels(),
              keywords: [],
              active: true,
              refuse_template: '',
              notes: null,
            },
            ...topics,
          ]);
          setSelectedId(id);
        }}
      />
      <View style={{ height: 12 }} />
      {topics.map((topic) => (
        <Pressable
          key={String(topic.id)}
          style={cmFormStyles.itemCard}
          onPress={() => setSelectedId(String(topic.id))}
        >
          <Text style={cmFormStyles.itemTitle}>
            {primaryLabel(topic.labels) || String(topic.id)}
          </Text>
        </Pressable>
      ))}
      {selected ? (
        <View style={cmFormStyles.card}>
          <Field
            label="Label (EN)"
            value={String(asRecord(selected.labels).en || '')}
            onChange={(v) =>
              patch(String(selected.id), {
                labels: { ...emptyLabels(), ...asRecord(selected.labels), en: v },
              })
            }
          />
          <Field
            label="Keywords (one per line)"
            value={listToText(selected.keywords)}
            onChange={(v) => patch(String(selected.id), { keywords: textToList(v) })}
            multiline
          />
          <Field
            label="Refuse template"
            value={String(selected.refuse_template || '')}
            onChange={(v) => patch(String(selected.id), { refuse_template: v })}
            multiline
          />
        </View>
      ) : null}
    </View>
  );
}
