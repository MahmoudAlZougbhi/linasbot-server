import { Pressable, Text, View } from 'react-native';

import { PrimaryButton } from '../../../components/PrimaryButton';
import { useI18n } from '../../../i18n/LanguageContext';
import { asRecordList, newId } from '../cmApi';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

const REQUEST_TYPES = ['APPOINTMENT', 'ORDER', 'OTHER'] as const;

type RequestType = (typeof REQUEST_TYPES)[number];

function str(value: unknown): string {
  return value == null ? '' : String(value);
}

function ruleType(item: Record<string, unknown>): RequestType {
  const raw = str(item.type).toUpperCase();
  if (REQUEST_TYPES.includes(raw as RequestType)) {
    return raw as RequestType;
  }
  return 'APPOINTMENT';
}

export function RequestsAppointmentsEditor({ payload, onChange }: Props) {
  const { tr } = useI18n();
  const rules = asRecordList(payload.rules);
  const setRules = (next: Record<string, unknown>[]) => onChange({ ...payload, rules: next });
  const patch = (id: string, data: Record<string, unknown>) =>
    setRules(rules.map((item) => (String(item.id) === id ? { ...item, ...data } : item)));

  const addRule = () => {
    const id = newId('req');
    setRules([
      {
        id,
        type: 'APPOINTMENT',
        enabled: true,
        name: '',
        notes: null,
      },
      ...rules,
    ]);
  };

  const typeLabel = (type: RequestType) => {
    if (type === 'APPOINTMENT') return tr('aiSetupRequestTypeAppointment');
    if (type === 'ORDER') return tr('aiSetupRequestTypeOrder');
    return tr('aiSetupRequestTypeOther');
  };

  return (
    <View>
      <Text style={cmFormStyles.rowTitle}>{tr('aiSetupRequestsHeading')}</Text>
      <Text style={cmFormStyles.hint}>{tr('aiSetupRequestsHint')}</Text>
      <PrimaryButton label={tr('aiSetupAddRequestRule')} variant="ghost" onPress={addRule} />
      <View style={{ height: 12 }} />
      {rules.map((item) => {
        const id = String(item.id);
        const selectedType = ruleType(item);
        return (
          <View key={id} style={cmFormStyles.card}>
            <Text style={cmFormStyles.itemTitle}>
              {str(item.name) || tr('aiSetupRequestUntitled')}
            </Text>
            <Text style={cmFormStyles.label}>{tr('aiSetupRequestType')}</Text>
            <View style={cmFormStyles.chipRow}>
              {REQUEST_TYPES.map((type) => {
                const on = selectedType === type;
                return (
                  <Pressable
                    key={type}
                    style={[cmFormStyles.chip, on && cmFormStyles.chipOn]}
                    onPress={() => patch(id, { type })}
                  >
                    <Text style={cmFormStyles.chipText}>{typeLabel(type)}</Text>
                  </Pressable>
                );
              })}
            </View>
            <Field
              label={tr('aiSetupRequestTitle')}
              value={str(item.name)}
              onChange={(v) => patch(id, { name: v })}
            />
            <Field
              label={tr('aiSetupRequestNote')}
              value={str(item.notes)}
              onChange={(v) => patch(id, { notes: v.trim() || null })}
              multiline
              hint={tr('aiSetupRequestNoteHint')}
            />
            <PrimaryButton
              label={tr('aiSetupDeleteRequest')}
              variant="ghost"
              onPress={() => setRules(rules.filter((rule) => String(rule.id) !== id))}
            />
          </View>
        );
      })}
      {rules.length === 0 ? <Text style={cmFormStyles.hint}>{tr('aiSetupRequestsEmpty')}</Text> : null}
    </View>
  );
}
