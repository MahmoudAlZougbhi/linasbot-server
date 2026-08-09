import { Modal, Pressable, ScrollView, Text, View } from 'react-native';
import { useState } from 'react';

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
      <Modal visible={open} animationType="slide" transparent onRequestClose={() => setOpen(false)}>
        <Pressable
          style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.35)', justifyContent: 'flex-end' }}
          onPress={() => setOpen(false)}
        >
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
        </Pressable>
      </Modal>
    </View>
  );
}
