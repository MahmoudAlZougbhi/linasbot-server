import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { PrimaryButton } from '../../../components/PrimaryButton';
import { asRecord, asRecordList, newId } from '../cmApi';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

const WEEKDAYS = [
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
  'sunday',
] as const;

const WEEKDAY_LABELS: Record<(typeof WEEKDAYS)[number], string> = {
  monday: 'Mon',
  tuesday: 'Tue',
  wednesday: 'Wed',
  thursday: 'Thu',
  friday: 'Fri',
  saturday: 'Sat',
  sunday: 'Sun',
};

function emptyDay(): Record<string, unknown> {
  return { closed: false, open: '', close: '' };
}

function emptySchedule(id: string): Record<string, unknown> {
  return {
    id,
    title: '',
    monday: emptyDay(),
    tuesday: emptyDay(),
    wednesday: emptyDay(),
    thursday: emptyDay(),
    friday: emptyDay(),
    saturday: emptyDay(),
    sunday: emptyDay(),
    notes: null,
  };
}

export function OpeningHoursEditor({ payload, onChange }: Props) {
  const items = asRecordList(payload.items);
  const [selectedId, setSelectedId] = useState<string | null>(
    items[0] ? String(items[0].id) : null,
  );
  const selected = items.find((i) => String(i.id) === selectedId) || items[0] || null;
  const setItems = (next: Record<string, unknown>[]) => onChange({ ...payload, items: next });

  const patch = (id: string, data: Record<string, unknown>) => {
    setItems(items.map((i) => (String(i.id) === id ? { ...i, ...data } : i)));
  };

  const patchDay = (id: string, dayKey: (typeof WEEKDAYS)[number], data: Record<string, unknown>) => {
    const row = items.find((i) => String(i.id) === id);
    if (!row) return;
    const day = { ...asRecord(row[dayKey]), ...data };
    patch(id, { [dayKey]: day });
  };

  return (
    <View>
      <Text style={cmFormStyles.hint}>
        Create named schedules (Men / Women / Branch). For each day set open→close or mark day off.
      </Text>
      <PrimaryButton
        label="Add schedule"
        variant="ghost"
        onPress={() => {
          const id = newId('hours');
          setItems([emptySchedule(id), ...items]);
          setSelectedId(id);
        }}
      />
      <View style={{ height: 12 }} />
      {items.map((item) => {
        const id = String(item.id);
        const active = selected && String(selected.id) === id;
        return (
          <Pressable
            key={id}
            style={[cmFormStyles.itemCard, active ? { borderColor: '#C4A574' } : null]}
            onPress={() => setSelectedId(id)}
          >
            <Text style={cmFormStyles.itemTitle}>{String(item.title || 'Untitled schedule')}</Text>
            <Text style={cmFormStyles.itemSub}>Mon–Sun hours</Text>
          </Pressable>
        );
      })}

      {selected ? (
        <View style={cmFormStyles.card}>
          <Field
            label="Title"
            value={String(selected.title || '')}
            onChange={(title) => patch(String(selected.id), { title })}
            placeholder="e.g. Men / Women / Branch Beirut"
          />
          {WEEKDAYS.map((dayKey) => {
            const day = asRecord(selected[dayKey]);
            const closed = Boolean(day.closed);
            return (
              <View key={dayKey} style={{ marginTop: 10 }}>
                <View style={cmFormStyles.row}>
                  <Text style={cmFormStyles.rowTitle}>{WEEKDAY_LABELS[dayKey]}</Text>
                  <Pressable
                    style={[cmFormStyles.chip, closed ? cmFormStyles.chipOn : null]}
                    onPress={() =>
                      patchDay(String(selected.id), dayKey, {
                        closed: !closed,
                        ...(closed ? {} : { open: '', close: '' }),
                      })
                    }
                  >
                    <Text style={cmFormStyles.chipText}>{closed ? 'Day off' : 'Open'}</Text>
                  </Pressable>
                </View>
                {!closed ? (
                  <View style={{ flexDirection: 'row', gap: 8 }}>
                    <View style={{ flex: 1 }}>
                      <Field
                        label="From"
                        value={String(day.open || '')}
                        onChange={(open) => patchDay(String(selected.id), dayKey, { open })}
                        placeholder="09:00"
                      />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Field
                        label="To"
                        value={String(day.close || '')}
                        onChange={(close) => patchDay(String(selected.id), dayKey, { close })}
                        placeholder="18:00"
                      />
                    </View>
                  </View>
                ) : null}
              </View>
            );
          })}
          <PrimaryButton
            label="Delete schedule"
            variant="ghost"
            onPress={() => {
              const next = items.filter((i) => String(i.id) !== String(selected.id));
              setItems(next);
              setSelectedId(next[0] ? String(next[0].id) : null);
            }}
          />
        </View>
      ) : null}
    </View>
  );
}
