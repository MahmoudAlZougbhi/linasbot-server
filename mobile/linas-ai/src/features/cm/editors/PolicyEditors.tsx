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

const ACTION_LABELS: Record<string, string> = {
  respond_facebook_dm: 'Facebook DMs',
  respond_instagram_dm: 'Instagram DMs',
  respond_facebook_comments: 'Facebook comments',
  respond_instagram_comments: 'Instagram comments',
  human_handoff: 'Human handoff',
  photo_analysis: 'Photo analysis',
  audio: 'Audio',
  likes: 'Likes',
  photo_animation: 'Photo animation',
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

export function ActionsEditor({ payload, onChange }: EditorProps) {
  const items = asRecordList(payload.items);
  const toggle = (id: string) =>
    onChange({
      ...payload,
      items: items.map((item) =>
        String(item.id) === id ? { ...item, enabled: !item.enabled } : item,
      ),
    });

  return (
    <View style={cmFormStyles.card}>
      {items.map((item) => {
        const id = String(item.id);
        return (
          <Pressable key={id} style={cmFormStyles.row} onPress={() => toggle(id)}>
            <Text style={cmFormStyles.rowTitle}>{ACTION_LABELS[id] || id}</Text>
            <Text style={cmFormStyles.chipText}>{item.enabled ? 'On' : 'Off'}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function AiLimitsEditor({ payload, onChange }: EditorProps) {
  const setNum = (key: string, value: string) => {
    const n = Number(value);
    onChange({ ...payload, [key]: Number.isFinite(n) ? n : 0 });
  };
  const toggle = (key: string) => onChange({ ...payload, [key]: !payload[key] });

  return (
    <View style={cmFormStyles.card}>
      {(
        [
          ['unlimited', 'Unlimited'],
          ['voice_processing_enabled', 'Voice / Audio'],
          ['image_analysis_enabled', 'Image analysis'],
          ['enforce_image_day', 'Enforce image/day'],
          ['enforce_image_week', 'Enforce image/week'],
          ['enforce_context_day', 'Enforce context/day'],
          ['enforce_context_week', 'Enforce context/week'],
        ] as const
      ).map(([key, label]) => (
        <Pressable key={key} style={cmFormStyles.row} onPress={() => toggle(key)}>
          <Text style={cmFormStyles.rowTitle}>{label}</Text>
          <Text style={cmFormStyles.chipText}>{payload[key] ? 'On' : 'Off'}</Text>
        </Pressable>
      ))}
      <Field
        label="Image per day"
        value={String(payload.image_per_day ?? '')}
        onChange={(v) => setNum('image_per_day', v)}
      />
      <Field
        label="Image per week"
        value={String(payload.image_per_week ?? '')}
        onChange={(v) => setNum('image_per_week', v)}
      />
      <Field
        label="Context lines per day"
        value={String(payload.context_lines_per_day ?? '')}
        onChange={(v) => setNum('context_lines_per_day', v)}
      />
      <Field
        label="Context lines per week"
        value={String(payload.context_lines_per_week ?? '')}
        onChange={(v) => setNum('context_lines_per_week', v)}
      />
    </View>
  );
}
