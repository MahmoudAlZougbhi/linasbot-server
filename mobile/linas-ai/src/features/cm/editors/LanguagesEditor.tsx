import { Pressable, Text, View } from 'react-native';

import { useI18n } from '../../../i18n/LanguageContext';
import { cmFormStyles } from '../cmFormStyles';

const LANGS = [
  { id: 'ar', label: 'Arabic' },
  { id: 'en', label: 'English' },
  { id: 'fr', label: 'French' },
  { id: 'franco', label: 'French-Arabic (Franco)' },
] as const;

/** Frozen answer map (matches backend RESPONSE_LANGUAGE_MAP). */
const RESPONSE_ROWS = [
  { fromLabel: 'Arabic', toLabel: 'Arabic' },
  { fromLabel: 'English', toLabel: 'English' },
  { fromLabel: 'French', toLabel: 'French' },
  { fromLabel: 'French-Arabic (Franco)', toLabel: 'Arabic (RTL)' },
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
    // Keep at least one language enabled.
    if (next.length === 0) return;
    onChange({ ...payload, supported_languages: next });
  };

  return (
    <View style={{ direction: isRtl ? 'rtl' : 'ltr' }}>
      <View style={cmFormStyles.card}>
        <Text style={cmFormStyles.label}>Languages the AI uses</Text>
        <Text style={cmFormStyles.hint}>
          Toggle off a language so the AI does not reply in it. Customers are answered only in enabled
          languages.
        </Text>
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
        <Text style={cmFormStyles.hint}>French-Arabic (Franco) questions always get Arabic-script answers.</Text>
      </View>
    </View>
  );
}
