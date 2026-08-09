import { Pressable, Text, View } from 'react-native';

import { useI18n } from '../../../i18n/LanguageContext';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';

const LANGS = [
  { id: 'ar', label: 'Arabic (RTL)' },
  { id: 'en', label: 'English' },
  { id: 'fr', label: 'French' },
  { id: 'franco', label: 'Franco / Arabizi' },
] as const;

const RESPONSE_ROWS = [
  { fromLabel: 'Arabic', toLabel: 'Arabic' },
  { fromLabel: 'English', toLabel: 'English' },
  { fromLabel: 'French', toLabel: 'French' },
  { fromLabel: 'Franco / Arabizi', toLabel: 'Arabic script (RTL)' },
];

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

export function LanguagesEditor({ payload, onChange }: Props) {
  const { isRtl } = useI18n();
  const supported = Array.isArray(payload.supported_languages)
    ? payload.supported_languages.map(String)
    : ['ar', 'en', 'fr', 'franco'];

  const toggle = (lang: string) => {
    const next = supported.includes(lang)
      ? supported.filter((x) => x !== lang)
      : [...supported, lang];
    onChange({ ...payload, supported_languages: next });
  };

  return (
    <View style={{ direction: isRtl ? 'rtl' : 'ltr' }}>
      <View style={cmFormStyles.card}>
        <Text style={cmFormStyles.label}>Supported languages</Text>
        <View style={cmFormStyles.chipRow}>
          {LANGS.map((lang) => {
            const on = supported.includes(lang.id);
            return (
              <Pressable
                key={lang.id}
                style={[cmFormStyles.chip, on && cmFormStyles.chipOn]}
                onPress={() => toggle(lang.id)}
              >
                <Text style={cmFormStyles.chipText}>{lang.label}</Text>
              </Pressable>
            );
          })}
        </View>
        <Text style={cmFormStyles.hint}>
          Franco questions always get Arabic-script answers. Arabic UI uses RTL layout.
        </Text>
      </View>

      <View style={cmFormStyles.card}>
        <Text style={cmFormStyles.label}>Answer language map</Text>
        {RESPONSE_ROWS.map((row) => (
          <View key={row.fromLabel} style={cmFormStyles.row}>
            <Text style={cmFormStyles.rowTitle}>
              {row.fromLabel} → {row.toLabel}
            </Text>
          </View>
        ))}
      </View>

      <View style={cmFormStyles.card}>
        <Text style={cmFormStyles.label}>Default / unknown language</Text>
        <View style={cmFormStyles.chipRow}>
          {LANGS.map((lang) => {
            const on = String(payload.default_language || 'ar') === lang.id;
            return (
              <Pressable
                key={lang.id}
                style={[cmFormStyles.chip, on && cmFormStyles.chipOn]}
                onPress={() => onChange({ ...payload, default_language: lang.id })}
              >
                <Text style={cmFormStyles.chipText}>{lang.label}</Text>
              </Pressable>
            );
          })}
        </View>
        <Field
          label="Mixed-language behavior"
          value={String(payload.mixed_language_behavior || '')}
          onChange={(v) => onChange({ ...payload, mixed_language_behavior: v })}
          multiline
        />
        <Field
          label="Unknown-language behavior"
          value={String(payload.unknown_language_behavior || '')}
          onChange={(v) => onChange({ ...payload, unknown_language_behavior: v })}
          multiline
        />
        <Field
          label="Notes"
          value={String(payload.notes || '')}
          onChange={(v) => onChange({ ...payload, notes: v })}
          multiline
        />
      </View>
    </View>
  );
}
