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
          <Field label="Name" value={String(selected.name || '')} onChange={(v) => patch(String(selected.id), { name: v })} />
          <Field label="Arabic" value={String(selected.ar || '')} onChange={(v) => patch(String(selected.id), { ar: v })} multiline />
          <Field label="English" value={String(selected.en || '')} onChange={(v) => patch(String(selected.id), { en: v })} multiline />
          <Field label="French" value={String(selected.fr || '')} onChange={(v) => patch(String(selected.id), { fr: v })} multiline />
        </View>
      ) : null}
    </View>
  );
}

export function BranchesEditor({ payload, onChange }: EditorProps) {
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
      <View style={cmFormStyles.card}>
        <Field
          label="Locations policy"
          value={String(payload.policy_text || '')}
          onChange={(v) => onChange({ ...payload, policy_text: v })}
          multiline
        />
      </View>
      <PrimaryButton
        label="Add location"
        variant="ghost"
        onPress={() => {
          const id = newId('branch');
          setItems([
            {
              id,
              labels: emptyLabels(),
              address: '',
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
          <Text style={cmFormStyles.itemSub}>{String(item.address || '')}</Text>
        </Pressable>
      ))}
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
            label="Address"
            value={String(selected.address || '')}
            onChange={(v) => patch(String(selected.id), { address: v })}
            multiline
          />
        </View>
      ) : null}
    </View>
  );
}

export function FaqEditor({ payload, onChange }: EditorProps) {
  const items = asRecordList(payload.items);
  const [selectedId, setSelectedId] = useState<string | null>(
    items[0] ? String(items[0].qa_group_id || items[0].id) : null,
  );
  const selected =
    items.find((i) => String(i.qa_group_id || i.id) === selectedId) || items[0] || null;

  const setItems = (next: Record<string, unknown>[]) => onChange({ ...payload, items: next });

  const patch = (groupId: string, data: Record<string, unknown>) =>
    setItems(
      items.map((i) =>
        String(i.qa_group_id || i.id) === groupId ? { ...i, ...data } : i,
      ),
    );

  const variantFor = (item: Record<string, unknown>, lang: string) => {
    const variants = asRecordList(item.variants);
    return variants.find((v) => String(v.language) === lang) || null;
  };

  const setVariant = (item: Record<string, unknown>, lang: string, field: 'question' | 'answer', value: string) => {
    const groupId = String(item.qa_group_id || item.id);
    const variants = asRecordList(item.variants);
    const existing = variants.find((v) => String(v.language) === lang);
    const nextVariants = existing
      ? variants.map((v) => (String(v.language) === lang ? { ...v, [field]: value } : v))
      : [...variants, { language: lang, question: '', answer: '', reviewed: false, is_auto_translated: false, [field]: value }];
    patch(groupId, { variants: nextVariants });
  };

  return (
    <View>
      <Text style={cmFormStyles.hint}>
        {items.length} FAQ groups. Mobile edits English + Arabic variants; full 4-lang review on web.
      </Text>
      <PrimaryButton
        label="Add FAQ"
        variant="ghost"
        onPress={() => {
          const id = newId('faq');
          setItems([
            {
              qa_group_id: id,
              variants: [
                { language: 'en', question: '', answer: '', reviewed: false, is_auto_translated: false },
                { language: 'ar', question: '', answer: '', reviewed: false, is_auto_translated: false },
              ],
              tags: [],
              notes: null,
              status: 'draft',
              source_language: 'en',
              reviewed: false,
              revision: 1,
            },
            ...items,
          ]);
          setSelectedId(id);
        }}
      />
      <View style={{ height: 12 }} />
      {items.map((item) => {
        const id = String(item.qa_group_id || item.id);
        const en = variantFor(item, 'en');
        return (
          <Pressable key={id} style={cmFormStyles.itemCard} onPress={() => setSelectedId(id)}>
            <Text style={cmFormStyles.itemTitle}>
              {String(en?.question || id)}
            </Text>
            <Text style={cmFormStyles.itemSub}>{String(item.status || 'draft')}</Text>
          </Pressable>
        );
      })}
      {selected ? (
        <View style={cmFormStyles.card}>
          <Field
            label="Question (EN)"
            value={String(variantFor(selected, 'en')?.question || '')}
            onChange={(v) => setVariant(selected, 'en', 'question', v)}
            multiline
          />
          <Field
            label="Answer (EN)"
            value={String(variantFor(selected, 'en')?.answer || '')}
            onChange={(v) => setVariant(selected, 'en', 'answer', v)}
            multiline
          />
          <Field
            label="Question (AR)"
            value={String(variantFor(selected, 'ar')?.question || '')}
            onChange={(v) => setVariant(selected, 'ar', 'question', v)}
            multiline
          />
          <Field
            label="Answer (AR)"
            value={String(variantFor(selected, 'ar')?.answer || '')}
            onChange={(v) => setVariant(selected, 'ar', 'answer', v)}
            multiline
          />
          <Field
            label="Status"
            value={String(selected.status || 'draft')}
            onChange={(v) => patch(String(selected.qa_group_id || selected.id), { status: v })}
          />
        </View>
      ) : null}
    </View>
  );
}

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
      {items.map((item) => (
        <Pressable key={String(item.id)} style={cmFormStyles.row} onPress={() => toggle(String(item.id))}>
          <Text style={cmFormStyles.rowTitle}>{String(item.id)}</Text>
          <Text style={cmFormStyles.chipText}>{item.enabled ? 'On' : 'Off'}</Text>
        </Pressable>
      ))}
      <Field
        label="Notes"
        value={String(payload.notes || '')}
        onChange={(v) => onChange({ ...payload, notes: v })}
        multiline
      />
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
          ['voice_processing_enabled', 'Voice processing'],
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
      <Field label="Image per day" value={String(payload.image_per_day ?? '')} onChange={(v) => setNum('image_per_day', v)} />
      <Field label="Image per week" value={String(payload.image_per_week ?? '')} onChange={(v) => setNum('image_per_week', v)} />
      <Field label="Context lines per day" value={String(payload.context_lines_per_day ?? '')} onChange={(v) => setNum('context_lines_per_day', v)} />
      <Field label="Context lines per week" value={String(payload.context_lines_per_week ?? '')} onChange={(v) => setNum('context_lines_per_week', v)} />
    </View>
  );
}

export function OffDaysEditor({ payload, onChange }: EditorProps) {
  const rules = asRecordList(payload.rules);
  return (
    <View>
      <View style={cmFormStyles.card}>
        <Field
          label="Timezone"
          value={String(payload.timezone || 'Asia/Beirut')}
          onChange={(v) => onChange({ ...payload, timezone: v })}
        />
        <Field
          label="Notes"
          value={String(payload.notes || '')}
          onChange={(v) => onChange({ ...payload, notes: v })}
          multiline
        />
      </View>
      <PrimaryButton
        label="Add weekly off day"
        variant="ghost"
        onPress={() =>
          onChange({
            ...payload,
            rules: [
              {
                id: newId('off'),
                kind: 'weekly',
                weekday: 0,
                date: '',
                start_date: '',
                end_date: '',
                reason: '',
                notes: null,
              },
              ...rules,
            ],
          })
        }
      />
      <View style={{ height: 12 }} />
      {rules.map((rule, index) => (
        <View key={String(rule.id)} style={cmFormStyles.card}>
          <Text style={cmFormStyles.itemTitle}>
            {String(rule.kind)} {rule.weekday != null ? `· weekday ${String(rule.weekday)}` : ''}
          </Text>
          <Field
            label="Weekday (0=Mon … 6=Sun)"
            value={rule.weekday == null ? '' : String(rule.weekday)}
            onChange={(v) => {
              const n = Number(v);
              const next = [...rules];
              next[index] = { ...rule, weekday: Number.isFinite(n) ? n : null };
              onChange({ ...payload, rules: next });
            }}
          />
          <Field
            label="Date (YYYY-MM-DD)"
            value={String(rule.date || '')}
            onChange={(v) => {
              const next = [...rules];
              next[index] = { ...rule, date: v, kind: v ? 'date' : rule.kind };
              onChange({ ...payload, rules: next });
            }}
          />
          <Field
            label="Reason"
            value={String(rule.reason || '')}
            onChange={(v) => {
              const next = [...rules];
              next[index] = { ...rule, reason: v };
              onChange({ ...payload, rules: next });
            }}
          />
        </View>
      ))}
    </View>
  );
}
