import { useRef } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';

import { colors, fonts, radii } from '../../theme';

type Props = {
  value: string;
  onChange: (next: string) => void;
};

const BOXES = [0, 1, 2, 3, 4, 5] as const;

/** Six OTP boxes; digits-only, auto-advance, teal border on the active box. */
export function AuthOtpRow({ value, onChange }: Props) {
  const refs = useRef<Array<TextInput | null>>([]);
  const digits = value.replace(/\D/g, '').slice(0, 6);

  function setAt(index: number, raw: string) {
    const chars = raw.replace(/\D/g, '');
    if (chars.length > 1) {
      onChange(chars.slice(0, 6));
      refs.current[Math.min(chars.length, 5)]?.focus();
      return;
    }
    const ch = chars.slice(-1);
    const next = (digits.slice(0, index) + ch + digits.slice(index + 1)).slice(0, 6);
    onChange(next);
    if (ch && index < 5) refs.current[index + 1]?.focus();
  }

  function onKey(index: number, key: string) {
    if (key === 'Backspace' && !digits[index] && index > 0) {
      onChange(digits.slice(0, index - 1));
      refs.current[index - 1]?.focus();
    }
  }

  return (
    <View style={styles.row}>
      {BOXES.map((i) => {
            const active = digits.length === 6 ? i === 5 : i === digits.length;
            return (
              <TextInput
                key={i}
                ref={(node) => {
                  refs.current[i] = node;
                }}
                value={digits[i] ?? ''}
                onChangeText={(text) => setAt(i, text)}
                onKeyPress={({ nativeEvent }) => onKey(i, nativeEvent.key)}
                keyboardType="number-pad"
                maxLength={1}
                selectTextOnFocus
                style={[styles.box, active && styles.boxOn]}
              />
            );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', justifyContent: 'space-between', gap: 8, marginBottom: 24 },
  box: {
    flex: 1,
    aspectRatio: 1,
    maxWidth: 52,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.sm,
    textAlign: 'center',
    fontFamily: fonts.bodyMedium,
    fontSize: 20,
    color: colors.text,
    backgroundColor: colors.surface,
  },
  boxOn: { borderColor: colors.accent, borderWidth: 1.5 },
});
