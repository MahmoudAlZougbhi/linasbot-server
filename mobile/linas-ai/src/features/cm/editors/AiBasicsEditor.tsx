import { View } from 'react-native';

import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

function str(payload: Record<string, unknown>, key: string): string {
  const v = payload[key];
  return typeof v === 'string' ? v : v == null ? '' : String(v);
}

export function AiBasicsEditor({ payload, onChange }: Props) {
  const set = (key: string, value: string) => onChange({ ...payload, [key]: value });

  return (
    <View style={cmFormStyles.card}>
      <Field label="AI display name" value={str(payload, 'assistant_name')} onChange={(v) => set('assistant_name', v)} />
      <Field label="Business name" value={str(payload, 'clinic_name')} onChange={(v) => set('clinic_name', v)} />
      <Field label="AI role" value={str(payload, 'ai_role')} onChange={(v) => set('ai_role', v)} />
      <Field
        label="Business purpose"
        value={str(payload, 'business_purpose')}
        onChange={(v) => set('business_purpose', v)}
        multiline
      />
      <Field
        label="Short introduction"
        value={str(payload, 'short_introduction')}
        onChange={(v) => set('short_introduction', v)}
        multiline
      />
      <Field
        label="Greeting behavior"
        value={str(payload, 'greeting_behavior')}
        onChange={(v) => set('greeting_behavior', v)}
        multiline
      />
      <Field
        label="Core business description"
        value={str(payload, 'identity_summary')}
        onChange={(v) => set('identity_summary', v)}
        multiline
      />
      <Field
        label="Additional owner instructions"
        value={str(payload, 'advanced_instructions')}
        onChange={(v) => set('advanced_instructions', v)}
        multiline
        hint="Business guidance only. Cannot override prices, hours, contacts, or restricted topics."
      />
      <Field label="Notes" value={str(payload, 'notes')} onChange={(v) => set('notes', v)} multiline />
    </View>
  );
}
