import { Pressable, ScrollView, Text, View } from 'react-native';
import { useState } from 'react';

import { AppModal } from '../../../components/AppModal';
import { ModalScrim } from '../../../components/ModalScrim';

import { colors } from '../../../theme';
import { cmFormStyles } from '../cmFormStyles';

type Props = {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
};

export function OptionPicker({ label, value, options, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const display = value.trim() || 'Select…';

  return (
    <View style={{ marginBottom: 12 }}>
      <Text style={cmFormStyles.label}>{label}</Text>
      <Pressable style={[cmFormStyles.chip, { alignSelf: 'stretch' }]} onPress={() => setOpen(true)}>
        <Text style={cmFormStyles.chipText}>{display}</Text>
      </Pressable>
      <AppModal visible={open} animationType="slide" onRequestClose={() => setOpen(false)}>
        <ModalScrim onPress={() => setOpen(false)}>
          <Pressable
            style={{
              maxHeight: '70%',
              backgroundColor: colors.surface,
              borderTopLeftRadius: 16,
              borderTopRightRadius: 16,
              padding: 16,
            }}
            onPress={(e) => e.stopPropagation()}
          >
            <Text style={[cmFormStyles.itemTitle, { marginBottom: 12 }]}>{label}</Text>
            <ScrollView>
              {options.map((opt) => {
                const on = opt === value;
                return (
                  <Pressable
                    key={opt}
                    style={[cmFormStyles.row, on && { backgroundColor: colors.accentSoft }]}
                    onPress={() => {
                      onChange(opt);
                      setOpen(false);
                    }}
                  >
                    <Text style={cmFormStyles.rowTitle}>{opt}</Text>
                    {on ? <Text style={cmFormStyles.chipText}>✓</Text> : null}
                  </Pressable>
                );
              })}
            </ScrollView>
          </Pressable>
        </ModalScrim>
      </AppModal>
    </View>
  );
}
