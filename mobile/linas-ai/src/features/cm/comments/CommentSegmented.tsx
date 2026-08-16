import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts } from '../../../theme';
import { CM_BORDER, CM_MUTED, CM_RADIUS_SM, CM_TEAL, CM_TEAL_DARK, CM_TEAL_SOFT } from './commentChrome';

export type SegmentOption<T extends string> = { id: T; label: string };

type Props<T extends string> = {
  label: string;
  value: T;
  options: SegmentOption<T>[];
  onChange: (value: T) => void;
};

export function CommentSegmented<T extends string>({ label, value, options, onChange }: Props<T>) {
  return (
    <View style={styles.wrap}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.row}>
        {options.map((option) => {
          const on = option.id === value;
          return (
            <Pressable
              key={option.id}
              onPress={() => onChange(option.id)}
              accessibilityRole="button"
              accessibilityState={{ selected: on }}
              style={({ pressed }) => [styles.chip, on && styles.chipOn, pressed && styles.pressed]}
            >
              <Text style={[styles.chipText, on && styles.chipTextOn]} numberOfLines={1}>
                {option.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 8, marginTop: 8 },
  label: {
    color: CM_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 15,
    fontWeight: '700',
  },
  row: { flexDirection: 'row', gap: 8 },
  chip: {
    flex: 1,
    minHeight: 44,
    borderWidth: 1.5,
    borderColor: CM_BORDER,
    borderRadius: CM_RADIUS_SM,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 6,
  },
  chipOn: { borderColor: CM_TEAL, backgroundColor: CM_TEAL_SOFT },
  chipText: {
    color: CM_MUTED,
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    fontWeight: '600',
    textAlign: 'center',
  },
  chipTextOn: { color: CM_TEAL },
  pressed: { opacity: 0.7 },
});
