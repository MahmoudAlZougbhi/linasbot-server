import { Pressable, StyleSheet, Text, TextInput, View, type KeyboardTypeOptions } from 'react-native';

import { AppModal } from '../../../components/AppModal';
import { fonts } from '../../../theme';
import { CM_BORDER, CM_MUTED, CM_RADIUS, CM_TEAL, CM_TEAL_DARK } from './commentChrome';

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

export function CommentTextModal({
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
            placeholderTextColor={CM_MUTED}
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
    borderRadius: CM_RADIUS,
    padding: 18,
    gap: 12,
  },
  title: { color: CM_TEAL_DARK, fontFamily: fonts.bodyMedium, fontSize: 17, fontWeight: '700' },
  input: {
    borderWidth: 1,
    borderColor: CM_BORDER,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontFamily: fonts.body,
    fontSize: 15,
    color: CM_TEAL_DARK,
  },
  row: { flexDirection: 'row', gap: 8, justifyContent: 'flex-end' },
  ghost: { paddingHorizontal: 14, paddingVertical: 10 },
  ghostText: { color: CM_MUTED, fontFamily: fonts.bodyMedium, fontSize: 15 },
  save: {
    backgroundColor: CM_TEAL,
    borderRadius: 8,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  saveText: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
});
