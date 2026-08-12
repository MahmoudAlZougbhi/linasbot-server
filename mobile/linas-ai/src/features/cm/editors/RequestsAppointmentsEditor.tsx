import { Pressable, Text, View } from 'react-native';

import { PrimaryButton } from '../../../components/PrimaryButton';
import { asRecord, asRecordList, emptyLabels, newId, primaryLabel } from '../cmApi';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

const REQUEST_TYPES = ['ORDER', 'APPOINTMENT', 'OTHER'] as const;

const BUILTIN_FIELD_IDS = [
  'preferred_date',
  'preferred_time',
  'phone',
  'email',
  'fulfillment',
  'address',
  'quantity',
  'notes',
  'service',
  'product',
  'branch',
  'customer_name',
] as const;

function asMessages(raw: unknown): Record<string, unknown> {
  return asRecord(raw);
}

function asAssignment(raw: unknown): Record<string, unknown> {
  return asRecord(raw);
}

function toggleType(enabled: string[], type: string): string[] {
  if (enabled.includes(type)) {
    return enabled.filter((t) => t !== type);
  }
  return [...enabled, type];
}

export function RequestsAppointmentsEditor({ payload, onChange }: Props) {
  const enabledTypes = Array.isArray(payload.enabled_types)
    ? payload.enabled_types.map(String)
    : [];
  const fields = asRecordList(payload.fields);
  const services = asRecordList(payload.services);
  const products = asRecordList(payload.products);
  const branches = asRecordList(payload.branches);
  const messages = asMessages(payload.messages);
  const assignment = asAssignment(payload.assignment_defaults);
  const prohibited = Array.isArray(payload.prohibited)
    ? payload.prohibited.map(String)
    : [];

  const patchMessages = (key: string, value: string) =>
    onChange({ ...payload, messages: { ...messages, [key]: value } });

  const setCatalog = (
    key: 'services' | 'products' | 'branches',
    next: Record<string, unknown>[],
  ) => onChange({ ...payload, [key]: next });

  const addCatalog = (key: 'services' | 'products' | 'branches', prefix: string) => {
    const list = key === 'services' ? services : key === 'products' ? products : branches;
    const id = newId(prefix);
    setCatalog(key, [
      { id, labels: { ...emptyLabels(), en: 'New item' }, enabled: true, notes: null },
      ...list,
    ]);
  };

  const patchCatalog = (
    key: 'services' | 'products' | 'branches',
    id: string,
    data: Record<string, unknown>,
  ) => {
    const list = key === 'services' ? services : key === 'products' ? products : branches;
    setCatalog(
      key,
      list.map((item) => (String(item.id) === id ? { ...item, ...data } : item)),
    );
  };

  const seedBuiltinFields = () => {
    const existing = new Set(fields.map((f) => String(f.id)));
    const seeded = BUILTIN_FIELD_IDS.filter((id) => !existing.has(id)).map((id, index) => ({
      id,
      labels: { ...emptyLabels(), en: id.replace(/_/g, ' ') },
      required: false,
      enabled: true,
      order: fields.length + index,
      applies_to: [],
      validation: id === 'phone' ? 'phone' : id === 'email' ? 'email' : '',
      notes: null,
    }));
    onChange({ ...payload, fields: [...fields, ...seeded] });
  };

  const patchField = (id: string, data: Record<string, unknown>) =>
    onChange({
      ...payload,
      fields: fields.map((f) => (String(f.id) === id ? { ...f, ...data } : f)),
    });

  return (
    <View>
      <Text style={cmFormStyles.hint}>
        Draft only. Customers are unaffected until you publish with the module enabled and at
        least one request type.
      </Text>
      <Pressable
        style={cmFormStyles.itemCard}
        onPress={() => onChange({ ...payload, module_enabled: !payload.module_enabled })}
      >
        <Text style={cmFormStyles.itemTitle}>
          Module {payload.module_enabled ? 'enabled' : 'disabled'}
        </Text>
        <Text style={cmFormStyles.hint}>Tap to toggle</Text>
      </Pressable>

      <Text style={cmFormStyles.label}>Enabled request types</Text>
      {REQUEST_TYPES.map((type) => {
        const on = enabledTypes.includes(type);
        return (
          <Pressable
            key={type}
            style={cmFormStyles.itemCard}
            onPress={() => onChange({ ...payload, enabled_types: toggleType(enabledTypes, type) })}
          >
            <Text style={cmFormStyles.itemTitle}>
              {on ? '✓ ' : ''}
              {type}
            </Text>
          </Pressable>
        );
      })}

      <Field
        label="Notification language"
        value={String(payload.notification_language || 'auto')}
        onChange={(v) => onChange({ ...payload, notification_language: v || 'auto' })}
        hint="auto | ar | en | fr | franco"
      />
      <Pressable
        style={cmFormStyles.itemCard}
        onPress={() => onChange({ ...payload, push_enabled: !payload.push_enabled })}
      >
        <Text style={cmFormStyles.itemTitle}>
          Push notifications {payload.push_enabled === false ? 'off' : 'on'}
        </Text>
      </Pressable>

      <Field
        label="Default assignee user id"
        value={String(assignment.default_assignee_user_id || '')}
        onChange={(v) =>
          onChange({
            ...payload,
            assignment_defaults: { ...assignment, default_assignee_user_id: v },
          })
        }
      />
      <Pressable
        style={cmFormStyles.itemCard}
        onPress={() =>
          onChange({
            ...payload,
            assignment_defaults: { ...assignment, auto_assign: !assignment.auto_assign },
          })
        }
      >
        <Text style={cmFormStyles.itemTitle}>
          Auto-assign {assignment.auto_assign ? 'on' : 'off'}
        </Text>
      </Pressable>

      <Text style={cmFormStyles.label}>Customer messages</Text>
      {(
        [
          ['acknowledgment', 'Acknowledgment'],
          ['appointment_confirmed', 'Appointment confirmed'],
          ['order_ready', 'Order ready'],
          ['completed', 'Completed'],
          ['cancelled', 'Cancellation'],
        ] as const
      ).map(([key, label]) => (
        <Field
          key={key}
          label={label}
          value={String(messages[key] || '')}
          onChange={(v) => patchMessages(key, v)}
          multiline
        />
      ))}

      <Field
        label="Prohibited / restricted topics (one per line)"
        value={prohibited.join('\n')}
        onChange={(v) =>
          onChange({
            ...payload,
            prohibited: v
              .split('\n')
              .map((line) => line.trim())
              .filter(Boolean),
          })
        }
        multiline
      />

      <PrimaryButton label="Seed common fields" onPress={seedBuiltinFields} variant="ghost" />
      <View style={{ height: 8 }} />
      {fields.map((item) => {
        const id = String(item.id);
        return (
          <View key={id} style={cmFormStyles.card}>
            <Text style={cmFormStyles.itemTitle}>{id}</Text>
            <Field
              label="Label (EN)"
              value={String(asRecord(item.labels).en || '')}
              onChange={(v) =>
                patchField(id, { labels: { ...emptyLabels(), ...asRecord(item.labels), en: v } })
              }
            />
            <Pressable
              style={cmFormStyles.itemCard}
              onPress={() => patchField(id, { required: !item.required })}
            >
              <Text style={cmFormStyles.hint}>{item.required ? 'Required' : 'Optional'}</Text>
            </Pressable>
            <Pressable
              style={cmFormStyles.itemCard}
              onPress={() => patchField(id, { enabled: item.enabled === false ? true : false })}
            >
              <Text style={cmFormStyles.hint}>
                Field {item.enabled === false ? 'disabled' : 'enabled'}
              </Text>
            </Pressable>
            <Field
              label="Order"
              value={String(item.order ?? 0)}
              onChange={(v) => patchField(id, { order: Number.parseInt(v, 10) || 0 })}
            />
            <Field
              label="Validation"
              value={String(item.validation || '')}
              onChange={(v) => patchField(id, { validation: v })}
              hint="phone | email | date | time | quantity | address | nonempty"
            />
          </View>
        );
      })}

      {(
        [
          ['services', 'Services', services],
          ['products', 'Products', products],
          ['branches', 'Branches', branches],
        ] as const
      ).map(([key, title, list]) => (
        <View key={key}>
          <Text style={cmFormStyles.label}>{title}</Text>
          <PrimaryButton
            label={`Add ${title.slice(0, -1).toLowerCase()}`}
            variant="ghost"
            onPress={() => addCatalog(key, key.slice(0, 3))}
          />
          {list.map((item) => {
            const id = String(item.id);
            return (
              <View key={id} style={cmFormStyles.card}>
                <Field
                  label="Label (EN)"
                  value={String(asRecord(item.labels).en || primaryLabel(item.labels) || '')}
                  onChange={(v) =>
                    patchCatalog(key, id, {
                      labels: { ...emptyLabels(), ...asRecord(item.labels), en: v },
                    })
                  }
                />
                <Pressable
                  style={cmFormStyles.itemCard}
                  onPress={() =>
                    patchCatalog(key, id, { enabled: item.enabled === false ? true : false })
                  }
                >
                  <Text style={cmFormStyles.hint}>
                    {item.enabled === false ? 'Disabled' : 'Enabled'}
                  </Text>
                </Pressable>
              </View>
            );
          })}
        </View>
      ))}

      <Field
        label="Notes"
        value={String(payload.notes || '')}
        onChange={(v) => onChange({ ...payload, notes: v || null })}
        multiline
      />
    </View>
  );
}
