import { useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { fonts, radii, spacing, useTheme } from '../../theme';
import { SFU_CARD_BORDER } from './smartFollowUpDesign';

export type DropdownOption = { value: string; label: string };

type Props = {
  value: string;
  options: DropdownOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  accessibilityLabel: string;
};

export function SmartFollowUpDropdown({
  value,
  options,
  onChange,
  disabled,
  accessibilityLabel,
}: Props) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  const selected = options.find((o) => o.value === value) ?? options[0];

  return (
    <>
      <Pressable
        disabled={disabled}
        onPress={() => setOpen(true)}
        style={[
          styles.trigger,
          {
            borderColor: SFU_CARD_BORDER,
            backgroundColor: colors.surface,
            opacity: disabled ? 0.55 : 1,
          },
        ]}
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel}
        accessibilityState={{ disabled: Boolean(disabled) }}
      >
        <Text style={[styles.triggerText, { color: colors.text }]} numberOfLines={1}>
          {selected?.label ?? '—'}
        </Text>
        <Ionicons name="chevron-down" size={16} color={colors.textMuted} />
      </Pressable>

      <Modal visible={open} animationType="slide" transparent onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)}>
          <Pressable
            style={[styles.sheet, { backgroundColor: colors.surface }]}
            onPress={(e) => e.stopPropagation()}
          >
            <Text style={[styles.sheetTitle, { color: colors.text }]}>{accessibilityLabel}</Text>
            <ScrollView>
              {options.map((opt) => {
                const on = opt.value === value;
                return (
                  <Pressable
                    key={opt.value}
                    onPress={() => {
                      onChange(opt.value);
                      setOpen(false);
                    }}
                    style={[styles.row, on && { backgroundColor: colors.accentSoft }]}
                    accessibilityRole="button"
                    accessibilityState={{ selected: on }}
                  >
                    <Text style={[styles.rowText, { color: colors.text }]}>{opt.label}</Text>
                    {on ? <Ionicons name="checkmark" size={18} color={colors.accent} /> : null}
                  </Pressable>
                );
              })}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  trigger: {
    flex: 1,
    minHeight: 40,
    borderWidth: 1,
    borderRadius: radii.sm,
    paddingHorizontal: 10,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 6,
  },
  triggerText: {
    flex: 1,
    fontFamily: fonts.body,
    fontSize: 14,
  },
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.35)',
    justifyContent: 'flex-end',
  },
  sheet: {
    maxHeight: '70%',
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    padding: spacing.md,
  },
  sheetTitle: {
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
    marginBottom: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 12,
    paddingHorizontal: 8,
    borderRadius: radii.sm,
  },
  rowText: {
    fontFamily: fonts.body,
    fontSize: 15,
  },
});
