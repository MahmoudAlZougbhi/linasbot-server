import { useEffect, useState } from 'react';
import { TextInput } from 'react-native';

import { formatClock12, parseClock12 } from './branchScheduleHelpers';
import { locStyles } from './locationHoursStyles';

type Props = {
  value: string;
  onChange: (hhmm: string) => void;
};

export function TimeField({ value, onChange }: Props) {
  const [text, setText] = useState(formatClock12(value) || value);

  useEffect(() => {
    setText(formatClock12(value) || value);
  }, [value]);

  return (
    <TextInput
      style={[locStyles.timeBox, locStyles.timeText]}
      value={text}
      onChangeText={setText}
      placeholder="9:00 AM"
      placeholderTextColor="#8A9A98"
      autoCapitalize="characters"
      autoCorrect={false}
      onBlur={() => {
        const parsed = parseClock12(text);
        if (parsed) {
          if (parsed !== value) onChange(parsed);
          setText(formatClock12(parsed));
          return;
        }
        if (!text.trim()) {
          if (value !== '') onChange('');
          setText('');
          return;
        }
        setText(formatClock12(value) || value);
      }}
    />
  );
}
