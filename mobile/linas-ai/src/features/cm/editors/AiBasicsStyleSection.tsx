import { Text, View } from 'react-native';

import { useI18n } from '../../../i18n/LanguageContext';
import { cmFormStyles } from '../cmFormStyles';
import { EMOJI_LEVEL_OPTIONS, FORMALITY_OPTIONS, TONE_OPTIONS } from '../styleOptions';
import { Field } from './Field';
import { OptionPicker } from './OptionPicker';

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

function str(payload: Record<string, unknown>, key: string): string {
  const v = payload[key];
  return typeof v === 'string' ? v : v == null ? '' : String(v);
}

export function AiBasicsStyleSection({ payload, onChange }: Props) {
  const { tr } = useI18n();
  const set = (key: string, value: unknown) => onChange({ ...payload, [key]: value });

  return (
    <View style={cmFormStyles.card}>
      <Text style={cmFormStyles.rowTitle}>{tr('aiSetupBasicsStyleHeading')}</Text>
      <Text style={cmFormStyles.hint}>{tr('aiSetupBasicsStyleHint')}</Text>
      <OptionPicker
        label={tr('aiSetupStyleTone')}
        value={str(payload, 'tone')}
        options={TONE_OPTIONS}
        onChange={(v) => set('tone', v)}
      />
      <OptionPicker
        label={tr('aiSetupStyleFormality')}
        value={str(payload, 'formality')}
        options={FORMALITY_OPTIONS}
        onChange={(v) => set('formality', v)}
      />
      <OptionPicker
        label={tr('aiSetupStyleEmoji')}
        value={str(payload, 'emoji_level')}
        options={EMOJI_LEVEL_OPTIONS}
        onChange={(v) => set('emoji_level', v)}
      />
      <Field
        label={tr('aiSetupStyleNote')}
        value={str(payload, 'style_body')}
        onChange={(v) => set('style_body', v)}
        multiline
        hint={tr('aiSetupStyleNoteHint')}
      />
    </View>
  );
}
