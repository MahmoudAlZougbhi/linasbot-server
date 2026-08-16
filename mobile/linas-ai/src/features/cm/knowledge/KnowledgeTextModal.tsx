import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { AppModal } from '../../../components/AppModal';
import { fonts } from '../../../theme';
import { KN_BORDER, KN_MUTED, KN_RADIUS, KN_TEAL, KN_TEAL_DARK } from './knowledgeChrome';

type Props = {
  visible: boolean;
  title: string;
  value: string;
  placeholder: string;
  saveLabel: string;
  cancelLabel: string;
  onChange: (value: string) => void;
  onSave: () => void;
  onClose: () => void;
};

export function KnowledgeTextModal({
  visible,
  title,
  value,
  placeholder,
  saveLabel,
  cancelLabel,
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
            placeholderTextColor={KN_MUTED}
            style={styles.input}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
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
    borderRadius: KN_RADIUS,
    padding: 18,
    gap: 12,
  },
  title: { color: KN_TEAL_DARK, fontFamily: fonts.bodyMedium, fontSize: 17, fontWeight: '700' },
  input: {
    borderWidth: 1,
    borderColor: KN_BORDER,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontFamily: fonts.body,
    fontSize: 15,
    color: KN_TEAL_DARK,
  },
  row: { flexDirection: 'row', gap: 8, justifyContent: 'flex-end' },
  ghost: { paddingHorizontal: 14, paddingVertical: 10 },
  ghostText: { color: KN_MUTED, fontFamily: fonts.bodyMedium, fontSize: 15 },
  save: {
    backgroundColor: KN_TEAL,
    borderRadius: 8,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  saveText: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
});
