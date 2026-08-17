import { StyleSheet, Text, View } from 'react-native';

import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { ClampedLongField } from '../ClampedLongField';
import { AiBasicsSegmented } from './AiBasicsSegmented';
import { AB_MUTED, AB_TEXT } from './aiBasicsChrome';
import { STYLE_EMOJI, STYLE_FORMALITY, STYLE_TONE } from './aiBasicsModel';

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  tr: (key: StringKey) => string;
};

function str(payload: Record<string, unknown>, key: string): string {
  const v = payload[key];
  return typeof v === 'string' ? v : v == null ? '' : String(v);
}

export function AiBasicsStyleTab({ payload, onChange, tr }: Props) {
  const set = (key: string, value: string) => onChange({ ...payload, [key]: value });

  return (
    <View style={styles.wrap}>
      <AiBasicsSegmented
        label={tr('aiSetupStyleTone')}
        value={str(payload, 'tone')}
        options={STYLE_TONE}
        onChange={(v) => set('tone', v)}
      />
      <AiBasicsSegmented
        label={tr('aiSetupStyleFormality')}
        value={str(payload, 'formality')}
        options={STYLE_FORMALITY}
        onChange={(v) => set('formality', v)}
      />
      <AiBasicsSegmented
        label={tr('aiSetupStyleEmoji')}
        value={str(payload, 'emoji_level')}
        options={STYLE_EMOJI}
        onChange={(v) => set('emoji_level', v)}
      />
      <ClampedLongField
        label={tr('aiSetupStyleNote')}
        value={str(payload, 'style_body')}
        onChange={(v) => set('style_body', v)}
        hint={tr('aiSetupStyleNoteHint')}
        labelStyle={styles.label}
        hintStyle={styles.hint}
        placeholderTextColor={AB_MUTED}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 16, paddingBottom: 12 },
  label: {
    color: AB_TEXT,
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 6,
  },
  hint: { color: AB_MUTED, fontFamily: fonts.body, fontSize: 12, marginTop: 6 },
});
