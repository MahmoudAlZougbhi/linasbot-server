import { Pressable, Text, View } from 'react-native';

import { PrimaryButton } from '../../../components/PrimaryButton';
import { useI18n } from '../../../i18n/LanguageContext';
import { asRecordList, newId } from '../cmApi';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';

type EditorProps = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

const TRIGGER_MODES = ['always', 'starts_with', 'any_keyword', 'session_start'] as const;

function str(value: unknown): string {
  return value == null ? '' : String(value);
}

export function GreetingsEditor({ payload, onChange }: EditorProps) {
  const { tr } = useI18n();
  const items = asRecordList(payload.items);
  const setItems = (next: Record<string, unknown>[]) => onChange({ ...payload, items: next });
  const patch = (id: string, data: Record<string, unknown>) =>
    setItems(items.map((i) => (String(i.id) === id ? { ...i, ...data } : i)));

  const addRule = () => {
    const id = newId('greet');
    setItems([
      {
        id,
        enabled: true,
        name: '',
        trigger_mode: 'starts_with',
        trigger_pattern: '',
        keywords: [],
        ar: '',
        en: '',
        fr: '',
        notes: null,
      },
      ...items,
    ]);
  };

  return (
    <View>
      <Text style={cmFormStyles.hint}>{tr('aiSetupGreetingsHint')}</Text>
      <Field
        label={tr('aiSetupGreetingsSectionNote')}
        value={str(payload.notes)}
        onChange={(v) => onChange({ ...payload, notes: v || null })}
        multiline
        hint={tr('aiSetupGreetingsSectionNoteHint')}
      />
      <PrimaryButton label={tr('aiSetupAddGreeting')} variant="ghost" onPress={addRule} />
      <View style={{ height: 12 }} />
      {items.map((item) => {
        const id = String(item.id);
        const mode = str(item.trigger_mode) || 'always';
        const enabled = item.enabled !== false;
        return (
          <View key={id} style={cmFormStyles.card}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text style={cmFormStyles.itemTitle}>{str(item.name) || tr('aiSetupGreetingUntitled')}</Text>
              <Pressable onPress={() => patch(id, { enabled: !enabled })}>
                <Text style={[cmFormStyles.hint, { marginBottom: 0, color: enabled ? '#059669' : '#9CA3AF' }]}>
                  {enabled ? tr('aiSetupGreetingEnabled') : tr('aiSetupGreetingDisabled')}
                </Text>
              </Pressable>
            </View>
            <Field
              label={tr('aiSetupGreetingTitle')}
              value={str(item.name)}
              onChange={(v) => patch(id, { name: v })}
            />
            <Text style={cmFormStyles.label}>{tr('aiSetupGreetingTrigger')}</Text>
            <View style={cmFormStyles.chipRow}>
              {TRIGGER_MODES.map((opt) => {
                const active = mode === opt;
                return (
                  <Pressable
                    key={opt}
                    style={[cmFormStyles.chip, active && cmFormStyles.chipOn]}
                    onPress={() => patch(id, { trigger_mode: opt })}
                  >
                    <Text style={cmFormStyles.chipText}>{tr(`aiSetupGreetingTrigger_${opt}`)}</Text>
                  </Pressable>
                );
              })}
            </View>
            {mode === 'starts_with' ? (
              <Field
                label={tr('aiSetupGreetingPattern')}
                value={str(item.trigger_pattern)}
                onChange={(v) => patch(id, { trigger_pattern: v })}
                hint={tr('aiSetupGreetingPatternHint')}
              />
            ) : null}
            {mode === 'any_keyword' ? (
              <Field
                label={tr('aiSetupGreetingKeywords')}
                value={Array.isArray(item.keywords) ? item.keywords.map(String).join(', ') : ''}
                onChange={(v) =>
                  patch(id, {
                    keywords: v
                      .split(',')
                      .map((x) => x.trim())
                      .filter(Boolean),
                  })
                }
                hint={tr('aiSetupGreetingKeywordsHint')}
              />
            ) : null}
            <Field
              label={tr('aiSetupGreetingText')}
              value={str(item.en)}
              onChange={(v) => patch(id, { en: v })}
              multiline
            />
            <PrimaryButton
              label={tr('aiSetupDeleteGreeting')}
              variant="ghost"
              onPress={() => setItems(items.filter((r) => String(r.id) !== id))}
            />
          </View>
        );
      })}
      {items.length === 0 ? <Text style={cmFormStyles.hint}>{tr('aiSetupGreetingsEmpty')}</Text> : null}
    </View>
  );
}
