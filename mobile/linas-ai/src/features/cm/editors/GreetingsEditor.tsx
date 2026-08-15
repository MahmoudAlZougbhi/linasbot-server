import { Text, View } from 'react-native';

import { PrimaryButton } from '../../../components/PrimaryButton';
import { useI18n } from '../../../i18n/LanguageContext';
import { asRecordList, newId } from '../cmApi';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';

type EditorProps = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  embedded?: boolean;
};

function str(value: unknown): string {
  return value == null ? '' : String(value);
}

/** Display note from notes field, falling back to legacy en greeting text. */
function ruleNote(item: Record<string, unknown>): string {
  const notes = str(item.notes);
  if (notes) return notes;
  return str(item.en);
}

/** Persist note to notes + en so runtime greeting resolution keeps working. */
function withNote(item: Record<string, unknown>, note: string): Record<string, unknown> {
  const trimmed = note.trim();
  return {
    ...item,
    notes: trimmed || null,
    en: trimmed,
    trigger_mode: item.trigger_mode || 'always',
    enabled: item.enabled !== false,
  };
}

export function GreetingsEditor({ payload, onChange, embedded = false }: EditorProps) {
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
        trigger_mode: 'always',
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
    <View style={embedded ? { marginTop: 12 } : undefined}>
      <Text style={cmFormStyles.rowTitle}>
        {embedded ? tr('aiSetupGreetingsHeading') : tr('aiSetupSec_dynamic_messages')}
      </Text>
      <Text style={cmFormStyles.hint}>{tr('aiSetupGreetingsHint')}</Text>
      <PrimaryButton label={tr('aiSetupAddGreetingRule')} variant="ghost" onPress={addRule} />
      <View style={{ height: 12 }} />
      {items.map((item) => {
        const id = String(item.id);
        return (
          <View key={id} style={cmFormStyles.card}>
            <Text style={cmFormStyles.itemTitle}>{str(item.name) || tr('aiSetupGreetingUntitled')}</Text>
            <Field
              label={tr('aiSetupGreetingTitle')}
              value={str(item.name)}
              onChange={(v) => patch(id, { name: v })}
            />
            <Field
              label={tr('aiSetupGreetingNote')}
              value={ruleNote(item)}
              onChange={(v) => patch(id, withNote(item, v))}
              multiline
              hint={tr('aiSetupGreetingNoteHint')}
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
