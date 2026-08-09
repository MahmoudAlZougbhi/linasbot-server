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

const DEST_TYPES = [
  { id: 'whatsapp', label: 'WhatsApp' },
  { id: 'phone', label: 'Phone / Call' },
  { id: 'url', label: 'Telegram / Link' },
  { id: 'email', label: 'Email' },
] as const;

export function HandoffEditor({ payload, onChange }: Props) {
  const contacts = asRecordList(payload.contacts);
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
  };

  const patchContact = (id: string, patch: Record<string, unknown>) =>
    setSection({
      contacts: contacts.map((item) => (String(item.id) === id ? { ...item, ...patch } : item)),
    });

  const selected = contacts.find((c) => String(c.id) === selectedId) || contacts[0] || null;

  return (
    <View>
      <Text style={cmFormStyles.hint}>
        Add contacts to point customers to when they ask for a human. Angry/cursing alerts stay in
        Notifications.
      </Text>
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
            <Text style={cmFormStyles.itemSub}>{String(item.destination_type || 'whatsapp')}</Text>
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
          <Text style={cmFormStyles.label}>Type</Text>
          <View style={cmFormStyles.chipRow}>
            {DEST_TYPES.map((t) => {
              const on = String(selected.destination_type || 'whatsapp') === t.id;
              return (
                <Pressable
                  key={t.id}
                  style={[cmFormStyles.chip, on && cmFormStyles.chipOn]}
                  onPress={() => patchContact(String(selected.id), { destination_type: t.id })}
                >
                  <Text style={cmFormStyles.chipText}>{t.label}</Text>
                </Pressable>
              );
            })}
          </View>
          <Field
            label="Number / link"
            value={String(selected.destination_value || selected.phone_e164 || '')}
            onChange={(v) =>
              patchContact(String(selected.id), { destination_value: v, phone_e164: v })
            }
            placeholder="+961… or https://t.me/…"
          />
        </View>
      ) : (
        <Text style={cmFormStyles.hint}>No contacts yet — tap Add contact.</Text>
      )}
    </View>
  );
}
