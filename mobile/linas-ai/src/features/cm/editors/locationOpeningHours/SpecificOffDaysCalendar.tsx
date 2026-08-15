import { useMemo, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { useI18n } from '../../../../i18n/LanguageContext';
import { newId } from '../../cmApi';
import { cmFormStyles } from '../../cmFormStyles';

type Props = {
  rules: Record<string, unknown>[];
  onChange: (rules: Record<string, unknown>[]) => void;
};

function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function toYmd(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function addMonths(d: Date, delta: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + delta, 1);
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export function SpecificOffDaysCalendar({ rules, onChange }: Props) {
  const { tr } = useI18n();
  const [monthCursor, setMonthCursor] = useState(() => startOfMonth(new Date()));

  const offDates = useMemo(() => {
    const set = new Set<string>();
    for (const rule of rules) {
      if (String(rule.kind) === 'date' && typeof rule.date === 'string' && rule.date) {
        set.add(rule.date);
      }
    }
    return set;
  }, [rules]);

  const toggleDate = (ymd: string) => {
    const existing = rules.find((r) => String(r.kind) === 'date' && String(r.date) === ymd);
    if (existing) {
      onChange(rules.filter((r) => String(r.id) !== String(existing.id)));
      return;
    }
    onChange([
      {
        id: newId('off'),
        kind: 'date',
        weekday: null,
        date: ymd,
        start_date: '',
        end_date: '',
        reason: 'Closed',
        notes: null,
      },
      ...rules,
    ]);
  };

  const year = monthCursor.getFullYear();
  const month = monthCursor.getMonth();
  const first = startOfMonth(monthCursor);
  const startPad = (first.getDay() + 6) % 7;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: Array<{ ymd: string; label: string } | null> = [];
  for (let i = 0; i < startPad; i += 1) cells.push(null);
  for (let day = 1; day <= daysInMonth; day += 1) {
    const d = new Date(year, month, day);
    cells.push({ ymd: toYmd(d), label: String(day) });
  }

  const title = monthCursor.toLocaleString('en', { month: 'long', year: 'numeric' });

  return (
    <View style={cmFormStyles.card}>
      <Text style={cmFormStyles.label}>{tr('aiSetupLocSpecialClosed')}</Text>
      <Text style={cmFormStyles.hint}>{tr('aiSetupLocSpecialClosedHint')}</Text>
      <View style={cmFormStyles.row}>
        <Pressable onPress={() => setMonthCursor(addMonths(monthCursor, -1))}>
          <Text style={cmFormStyles.chipText}>‹</Text>
        </Pressable>
        <Text style={cmFormStyles.itemTitle}>{title}</Text>
        <Pressable onPress={() => setMonthCursor(addMonths(monthCursor, 1))}>
          <Text style={cmFormStyles.chipText}>›</Text>
        </Pressable>
      </View>
      <View style={{ flexDirection: 'row', marginTop: 8 }}>
        {WEEKDAYS.map((w) => (
          <Text key={w} style={[cmFormStyles.hint, { flex: 1, textAlign: 'center' }]}>
            {w}
          </Text>
        ))}
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        {cells.map((cell, index) => {
          if (!cell) {
            return <View key={`pad-${index}`} style={{ width: '14.28%', aspectRatio: 1 }} />;
          }
          const off = offDates.has(cell.ymd);
          return (
            <Pressable
              key={cell.ymd}
              onPress={() => toggleDate(cell.ymd)}
              style={{
                width: '14.28%',
                aspectRatio: 1,
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 8,
                backgroundColor: off ? '#FECACA' : 'transparent',
                borderWidth: off ? 1 : 0,
                borderColor: '#EF4444',
              }}
            >
              <Text
                style={[
                  cmFormStyles.rowTitle,
                  { textAlign: 'center', color: off ? '#B91C1C' : undefined },
                ]}
              >
                {cell.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
      <Text style={[cmFormStyles.hint, { marginTop: 12 }]}>
        {offDates.size} closed day{offDates.size === 1 ? '' : 's'}
      </Text>
    </View>
  );
}
