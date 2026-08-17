import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts } from '../../../theme';
import { AB_BORDER, AB_FOREST, AB_RADIUS_SM, AB_TEXT } from './aiBasicsChrome';

type Props = {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
};

export function AiBasicsSegmented({ label, value, options, onChange }: Props) {
  return (
    <View style={styles.wrap}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.row}>
        {options.map((option) => {
          const on = value === option;
          return (
            <Pressable
              key={option}
              onPress={() => onChange(option)}
              accessibilityRole="button"
              accessibilityState={{ selected: on }}
              style={[styles.chip, on && styles.chipOn]}
            >
              <Text style={[styles.chipText, on && styles.chipTextOn]}>{option}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 8 },
  label: { color: AB_TEXT, fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '700' },
  row: { flexDirection: 'row', gap: 8 },
  chip: {
    flex: 1,
    minHeight: 40,
    borderRadius: AB_RADIUS_SM,
    borderWidth: 1,
    borderColor: AB_BORDER,
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
  chipOn: { backgroundColor: AB_FOREST, borderColor: AB_FOREST },
  chipText: { color: AB_TEXT, fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '600' },
  chipTextOn: { color: '#FFFFFF' },
});
