import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { PrimaryButton } from '../../../components/PrimaryButton';
import { asRecordList, newId } from '../cmApi';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

export function HandoffEditor({ payload, onChange }: Props) {
  const contacts = asRecordList(payload.contacts);
  const matrix = asRecordList(payload.matrix);
  const [tab, setTab] = useState<'contacts' | 'matrix'>('contacts');
  const [selectedId, setSelectedId] = useState<string | null>(
    contacts[0] ? String(contacts[0].id) : null,
  );

  const setSection = (patch: Record<string, unknown>) => onChange({ ...payload, ...patch });

  const addContact = () => {
    const id = newId('contact');
    setSection({
      contacts: [
        {
          id,
          destination_type: 'whatsapp',
          destination_value: '',
          phone_e164: '',
          label: '',
          branch_id: null,
          gender: 'any',
          topic_id: null,
          notes: null,
        },
        ...contacts,
      ],
    });
    setSelectedId(id);
    setTab('contacts');
  };

  const patchContact = (id: string, patch: Record<string, unknown>) =>
    setSection({
      contacts: contacts.map((item) => (String(item.id) === id ? { ...item, ...patch } : item)),
    });

  const selected = contacts.find((c) => String(c.id) === selectedId) || contacts[0] || null;

  return (
    <View>
      <View style={cmFormStyles.card}>
        <Field
          label="Booking & appointment policy"
          value={String(payload.policy_text || '')}
          onChange={(v) => setSection({ policy_text: v })}
          multiline
        />
      </View>
      <View style={cmFormStyles.chipRow}>
        <Pressable
          style={[cmFormStyles.chip, tab === 'contacts' && cmFormStyles.chipOn]}
          onPress={() => setTab('contacts')}
        >
          <Text style={cmFormStyles.chipText}>Contacts ({contacts.length})</Text>
        </Pressable>
        <Pressable
          style={[cmFormStyles.chip, tab === 'matrix' && cmFormStyles.chipOn]}
          onPress={() => setTab('matrix')}
        >
          <Text style={cmFormStyles.chipText}>Routes ({matrix.length})</Text>
        </Pressable>
      </View>

      {tab === 'contacts' ? (
        <>
          <PrimaryButton label="Add contact" onPress={addContact} variant="ghost" />
          <View style={{ height: 12 }} />
          {contacts.map((item) => {
            const id = String(item.id);
            const active = selected && String(selected.id) === id;
            return (
              <Pressable
                key={id}
                style={[cmFormStyles.itemCard, active && { borderColor: '#2563EB' }]}
                onPress={() => setSelectedId(id)}
              >
                <Text style={cmFormStyles.itemTitle}>
                  {String(item.label || item.destination_value || id)}
                </Text>
                <Text style={cmFormStyles.itemSub}>
                  {String(item.destination_type || 'whatsapp')}
                </Text>
              </Pressable>
            );
          })}
          {selected ? (
            <View style={cmFormStyles.card}>
              <Field
                label="Label"
                value={String(selected.label || '')}
                onChange={(v) => patchContact(String(selected.id), { label: v })}
              />
              <Field
                label="Destination type (phone / whatsapp / email / url)"
                value={String(selected.destination_type || 'whatsapp')}
                onChange={(v) => patchContact(String(selected.id), { destination_type: v })}
              />
              <Field
                label="Destination value"
                value={String(selected.destination_value || selected.phone_e164 || '')}
                onChange={(v) =>
                  patchContact(String(selected.id), { destination_value: v, phone_e164: v })
                }
              />
              <Field
                label="Notes"
                value={String(selected.notes || '')}
                onChange={(v) => patchContact(String(selected.id), { notes: v })}
                multiline
              />
            </View>
          ) : null}
        </>
      ) : (
        <View style={cmFormStyles.card}>
          <Text style={cmFormStyles.hint}>
            {matrix.length} routing rows. Edit contact destinations above; full matrix authoring is
            on the web dashboard.
          </Text>
          {matrix.map((row) => (
            <View key={String(row.id)} style={cmFormStyles.row}>
              <Text style={cmFormStyles.rowTitle}>
                {String(row.contact_id || row.id)}
                {row.enabled === false ? ' (disabled)' : ''}
              </Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}
