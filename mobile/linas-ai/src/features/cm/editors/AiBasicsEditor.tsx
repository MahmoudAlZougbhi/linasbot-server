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
      <Field label="AI role" value={str(payload, 'ai_role')} onChange={(v) => set('ai_role', v)} />
      <Field
        label="Business purpose"
        value={str(payload, 'business_purpose')}
        onChange={(v) => set('business_purpose', v)}
        multiline
        hint="Maps to business_purpose in the CM draft schema."
      />
      <Field
        label="Short introduction"
        value={str(payload, 'short_introduction')}
        onChange={(v) => set('short_introduction', v)}
        multiline
      />
    </View>
  );
}
