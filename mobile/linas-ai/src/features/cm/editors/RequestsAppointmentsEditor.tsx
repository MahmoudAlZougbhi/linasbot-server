import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../../api/client';
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
const PreviewSchema = z.object({ success: z.boolean(), preview: z.record(z.string(), z.unknown()).optional() }).passthrough();

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

function destinationFromType(type: RequestType): string {
  if (type === 'APPOINTMENT') return 'appointment';
  if (type === 'ORDER') return 'order';
  return 'general';
}

function fieldList(preview: Record<string, unknown>): string {
  const rows = Array.isArray(preview.required_information) ? preview.required_information : [];
  return rows
    .map((row) => {
      if (!row || typeof row !== 'object') return '';
      const rec = row as Record<string, unknown>;
      return str(rec.label || rec.key);
    })
    .filter(Boolean)
    .join(', ');
}

export function RequestsAppointmentsEditor({ payload, onChange }: Props) {
  const { tr } = useI18n();
  const rules = asRecordList(payload.rules);
  const [previewById, setPreviewById] = useState<Record<string, Record<string, unknown>>>({});
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

  const runPreview = async (item: Record<string, unknown>) => {
    const id = String(item.id);
    const selectedType = ruleType(item);
    try {
      const data = await apiFetch('/api/cm/request-graphs/preview', {
        method: 'POST',
        schema: PreviewSchema,
        body: JSON.stringify({
          title: str(item.name),
          source_text: `${str(item.name)}\n${str(item.notes)}`.trim(),
          destination: destinationFromType(selectedType),
        }),
      });
      setPreviewById((current) => ({ ...current, [id]: data.preview || {} }));
    } catch {
      setPreviewById((current) => ({ ...current, [id]: { error: 'preview_failed' } }));
    }
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
        const preview = previewById[id];
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
              label={tr('aiSetupRequestPreview')}
              variant="ghost"
              onPress={() => {
                void runPreview(item);
              }}
            />
            {preview ? (
              <View style={{ marginTop: 8 }}>
                {preview.needs_owner_clarification ? (
                  <Text style={cmFormStyles.hint}>{tr('aiSetupRequestNeedsClarification')}</Text>
                ) : (
                  <>
                    <Text style={cmFormStyles.hint}>
                      {tr('aiSetupRequestDestination')}: {str(preview.destination)}
                    </Text>
                    <Text style={cmFormStyles.hint}>
                      {tr('aiSetupRequestRequiredFields')}: {fieldList(preview) || '—'}
                    </Text>
                    <Text style={cmFormStyles.hint}>{tr('aiSetupRequestConfirmHint')}</Text>
                  </>
                )}
              </View>
            ) : null}
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
