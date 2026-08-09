import { View } from 'react-native';

import { cmFormStyles } from '../cmFormStyles';
import { EMOJI_LEVEL_OPTIONS, FORMALITY_OPTIONS, TONE_OPTIONS } from '../styleOptions';
import { OptionPicker } from './OptionPicker';

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

export function StyleEditor({ payload, onChange }: Props) {
  const set = (key: string, value: unknown) => onChange({ ...payload, [key]: value });

  return (
    <View style={cmFormStyles.card}>
      <OptionPicker
        label="Tone"
        value={String(payload.tone || '')}
        options={TONE_OPTIONS}
        onChange={(v) => set('tone', v)}
      />
      <OptionPicker
        label="Formality"
        value={String(payload.formality || '')}
        options={FORMALITY_OPTIONS}
        onChange={(v) => set('formality', v)}
      />
      <OptionPicker
        label="Emoji level"
        value={String(payload.emoji_level || '')}
        options={EMOJI_LEVEL_OPTIONS}
        onChange={(v) => set('emoji_level', v)}
      />
    </View>
  );
}
