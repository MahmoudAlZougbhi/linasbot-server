import { Pressable, Text, View } from 'react-native';

import { listToText, textToList } from '../cmApi';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

function Toggle({
  label,
  value,
  onToggle,
}: {
  label: string;
  value: boolean;
  onToggle: () => void;
}) {
  return (
    <Pressable style={cmFormStyles.row} onPress={onToggle}>
      <Text style={cmFormStyles.rowTitle}>{label}</Text>
      <Text style={cmFormStyles.chipText}>{value ? 'On' : 'Off'}</Text>
    </Pressable>
  );
}

export function StyleEditor({ payload, onChange }: Props) {
  const set = (key: string, value: unknown) => onChange({ ...payload, [key]: value });

  return (
    <View style={cmFormStyles.card}>
      <Field label="Tone" value={String(payload.tone || '')} onChange={(v) => set('tone', v)} />
      <Field
        label="Formality"
        value={String(payload.formality || '')}
        onChange={(v) => set('formality', v)}
      />
      <Field
        label="Response length"
        value={String(payload.response_length || '')}
        onChange={(v) => set('response_length', v)}
      />
      <Field
        label="Emoji level"
        value={String(payload.emoji_level || '')}
        onChange={(v) => set('emoji_level', v)}
      />
      <Toggle
        label="Ask one question at a time"
        value={Boolean(payload.one_question_at_a_time)}
        onToggle={() => set('one_question_at_a_time', !payload.one_question_at_a_time)}
      />
      <Toggle
        label="Use customer name when known"
        value={Boolean(payload.use_customer_name)}
        onToggle={() => set('use_customer_name', !payload.use_customer_name)}
      />
      <Field
        label="Preferred terms (one per line)"
        value={listToText(payload.preferred_terms)}
        onChange={(v) => set('preferred_terms', textToList(v))}
        multiline
      />
      <Field
        label="Example replies (one per line)"
        value={listToText(payload.example_replies)}
        onChange={(v) => set('example_replies', textToList(v))}
        multiline
      />
      <Field
        label="Do (one per line)"
        value={listToText(payload.do_list)}
        onChange={(v) => set('do_list', textToList(v))}
        multiline
      />
      <Field
        label="Don't (one per line)"
        value={listToText(payload.dont_list)}
        onChange={(v) => set('dont_list', textToList(v))}
        multiline
      />
      <Field
        label="Style notes"
        value={String(payload.style_body || '')}
        onChange={(v) => set('style_body', v)}
        multiline
      />
      <Field label="Notes" value={String(payload.notes || '')} onChange={(v) => set('notes', v)} multiline />
    </View>
  );
}
