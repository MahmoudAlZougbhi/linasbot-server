import { Text, View } from 'react-native';

import { useI18n } from '../../../i18n/LanguageContext';
import { cmFormStyles } from '../cmFormStyles';
import { AiBasicsStyleSection } from './AiBasicsStyleSection';
import { Field } from './Field';
import { GreetingsEditor } from './GreetingsEditor';

type Props = {
  basicsPayload: Record<string, unknown>;
  stylePayload: Record<string, unknown>;
  greetingsPayload: Record<string, unknown>;
  onBasicsChange: (next: Record<string, unknown>) => void;
  onStyleChange: (next: Record<string, unknown>) => void;
  onGreetingsChange: (next: Record<string, unknown>) => void;
};

function str(payload: Record<string, unknown>, key: string): string {
  const v = payload[key];
  return typeof v === 'string' ? v : v == null ? '' : String(v);
}

export function AiBasicsEditor({
  basicsPayload,
  stylePayload,
  greetingsPayload,
  onBasicsChange,
  onStyleChange,
  onGreetingsChange,
}: Props) {
  const { tr } = useI18n();
  const setBasics = (key: string, value: string) =>
    onBasicsChange({ ...basicsPayload, [key]: value });

  return (
    <View>
      <View style={cmFormStyles.card}>
        <Text style={cmFormStyles.rowTitle}>{tr('aiSetupBasicsIdentityHeading')}</Text>
        <Field
          label={tr('aiSetupBusinessName')}
          value={str(basicsPayload, 'clinic_name')}
          onChange={(v) => setBasics('clinic_name', v)}
        />
        <Field
          label={tr('aiSetupAiName')}
          value={str(basicsPayload, 'assistant_name')}
          onChange={(v) => setBasics('assistant_name', v)}
        />
        <Field
          label={tr('aiSetupAiRole')}
          value={str(basicsPayload, 'ai_role')}
          onChange={(v) => setBasics('ai_role', v)}
        />
        <Field
          label={tr('aiSetupBusinessPurpose')}
          value={str(basicsPayload, 'business_purpose')}
          onChange={(v) => setBasics('business_purpose', v)}
          multiline
        />
        <Field
          label={tr('aiSetupShortIntro')}
          value={str(basicsPayload, 'short_introduction')}
          onChange={(v) => setBasics('short_introduction', v)}
          multiline
        />
      </View>
      <AiBasicsStyleSection payload={stylePayload} onChange={onStyleChange} />
      <View style={cmFormStyles.card}>
        <GreetingsEditor payload={greetingsPayload} onChange={onGreetingsChange} embedded />
      </View>
    </View>
  );
}
