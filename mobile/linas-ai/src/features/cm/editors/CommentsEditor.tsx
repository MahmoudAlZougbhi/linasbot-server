import { Pressable, Text, View } from 'react-native';

import { PrimaryButton } from '../../../components/PrimaryButton';
import { asRecordList, newId } from '../cmApi';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

const ACTIONS: Array<{ value: string; label: string }> = [
  { value: 'reply_comment', label: 'Reply on comment' },
  { value: 'reply_dm', label: 'Reply via DM' },
  { value: 'ignore', label: 'Ignore' },
];

export function CommentsEditor({ payload, onChange }: Props) {
  const rules = asRecordList(payload.rules);

  const setRules = (next: Record<string, unknown>[]) => onChange({ ...payload, rules: next });

  const add = () => {
    const id = newId('crule');
    setRules([
      {
        id,
        enabled: true,
        name: 'New rule',
        match_mode: 'any_keyword',
        keywords: [],
        pattern: '',
        post_id: '',
        channel: 'any',
        action: 'reply_comment',
        reply_template: '',
        notes: null,
      },
      ...rules,
    ]);
  };

  const patch = (id: string, patchData: Record<string, unknown>) =>
    setRules(rules.map((item) => (String(item.id) === id ? { ...item, ...patchData } : item)));

  return (
    <View>
      <Field
        label="Default when no rule matches"
        value={String(payload.default_action || 'reply_comment')}
        onChange={(v) => onChange({ ...payload, default_action: v === 'ignore' ? 'ignore' : 'reply_comment' })}
        hint="reply_comment or ignore"
      />
      <Field
        label="Policy text (AI guidance)"
        value={String(payload.policy_text || '')}
        onChange={(v) => onChange({ ...payload, policy_text: v })}
        multiline
      />
      <PrimaryButton label="Add comment rule" onPress={add} variant="ghost" />
      <View style={{ height: 12 }} />
      {rules.map((item) => {
        const id = String(item.id);
        return (
          <View key={id} style={cmFormStyles.card}>
            <Field label="Name" value={String(item.name || '')} onChange={(v) => patch(id, { name: v })} />
            <Field
              label="Keywords (comma-separated)"
              value={Array.isArray(item.keywords) ? item.keywords.map(String).join(', ') : ''}
              onChange={(v) =>
                patch(id, {
                  keywords: v
                    .split(',')
                    .map((x) => x.trim())
                    .filter(Boolean),
                })
              }
            />
            <Field
              label="Optional post / media id"
              value={String(item.post_id || '')}
              onChange={(v) => patch(id, { post_id: v })}
            />
            <Text style={cmFormStyles.hint}>Action</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
              {ACTIONS.map((opt) => {
                const active = String(item.action || 'reply_comment') === opt.value;
                return (
                  <Pressable
                    key={opt.value}
                    style={[cmFormStyles.itemCard, active && { borderColor: '#2563EB' }]}
                    onPress={() => patch(id, { action: opt.value })}
                  >
                    <Text style={cmFormStyles.itemTitle}>{opt.label}</Text>
                  </Pressable>
                );
              })}
            </View>
            <Field
              label={String(item.action) === 'reply_dm' ? 'DM message (required)' : 'Fixed reply (optional)'}
              value={String(item.reply_template || '')}
              onChange={(v) => patch(id, { reply_template: v })}
              multiline
            />
            <PrimaryButton
              label={item.enabled === false ? 'Enable rule' : 'Disable rule'}
              variant="ghost"
              onPress={() => patch(id, { enabled: item.enabled === false })}
            />
            <PrimaryButton
              label="Delete rule"
              variant="ghost"
              onPress={() => setRules(rules.filter((r) => String(r.id) !== id))}
            />
          </View>
        );
      })}
      {rules.length === 0 ? <Text style={cmFormStyles.hint}>No rules — uses default action.</Text> : null}
    </View>
  );
}
