import { Pressable, StyleSheet, Text, TextInput, View, type KeyboardTypeOptions } from 'react-native';

import { AppModal } from '../../components/AppModal';
import { fonts } from '../../theme';
import { SV_BORDER, SV_MUTED, SV_RADIUS, SV_TEAL, SV_TEAL_DARK } from './serviceChrome';

type Props = {
  visible: boolean;
  title: string;
  value: string;
  placeholder: string;
  saveLabel: string;
  cancelLabel: string;
  keyboardType?: KeyboardTypeOptions;
  onChange: (value: string) => void;
  onSave: () => void;
  onClose: () => void;
};

export function ServiceTextModal({
  visible,
  title,
  value,
  placeholder,
  saveLabel,
  cancelLabel,
  keyboardType = 'default',
  onChange,
  onSave,
  onClose,
}: Props) {
  return (
    <AppModal visible={visible} animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.scrim} onPress={onClose}>
        <Pressable style={styles.sheet} onPress={() => undefined}>
          <Text style={styles.title}>{title}</Text>
          <TextInput
            value={value}
            onChangeText={onChange}
            placeholder={placeholder}
            placeholderTextColor={SV_MUTED}
            style={styles.input}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType={keyboardType}
          />
          <View style={styles.row}>
            <Pressable onPress={onClose} style={styles.ghost}>
              <Text style={styles.ghostText}>{cancelLabel}</Text>
            </Pressable>
            <Pressable onPress={onSave} style={styles.save}>
              <Text style={styles.saveText}>{saveLabel}</Text>
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

const styles = StyleSheet.create({
  scrim: {
    flex: 1,
    backgroundColor: 'rgba(16, 34, 26, 0.45)',
    justifyContent: 'center',
    padding: 24,
  },
  sheet: {
    backgroundColor: '#FFFFFF',
    borderRadius: SV_RADIUS,
    padding: 18,
    gap: 12,
  },
  title: { color: SV_TEAL_DARK, fontFamily: fonts.bodyMedium, fontSize: 17, fontWeight: '700' },
  input: {
    borderWidth: 1,
    borderColor: SV_BORDER,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontFamily: fonts.body,
    fontSize: 15,
    color: SV_TEAL_DARK,
  },
  row: { flexDirection: 'row', gap: 8, justifyContent: 'flex-end' },
  ghost: { paddingHorizontal: 14, paddingVertical: 10 },
  ghostText: { color: SV_MUTED, fontFamily: fonts.bodyMedium, fontSize: 15 },
  save: {
    backgroundColor: SV_TEAL,
    borderRadius: 8,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  saveText: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
});
