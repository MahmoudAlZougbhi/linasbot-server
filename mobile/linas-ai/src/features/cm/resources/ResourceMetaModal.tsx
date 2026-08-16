import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { AppModal } from '../../../components/AppModal';
import { fonts } from '../../../theme';

const TEAL = '#107C75';
const TEAL_DARK = '#0F4C4A';
const MUTED = '#6B7280';
const BORDER = '#D7E4E2';

export type ResourceMetaModalProps = {
  visible: boolean;
  heading: string;
  preview?: string;
  showUrl?: boolean;
  url: string;
  title: string;
  description: string;
  error?: string | null;
  titleLabel: string;
  descriptionLabel: string;
  urlLabel: string;
  titlePlaceholder: string;
  descriptionPlaceholder: string;
  urlPlaceholder: string;
  saveLabel: string;
  cancelLabel: string;
  onChangeUrl: (value: string) => void;
  onChangeTitle: (value: string) => void;
  onChangeDescription: (value: string) => void;
  onSave: () => void;
  onClose: () => void;
};

export function ResourceMetaModal({
  visible,
  heading,
  preview,
  showUrl = false,
  url,
  title,
  description,
  error,
  titleLabel,
  descriptionLabel,
  urlLabel,
  titlePlaceholder,
  descriptionPlaceholder,
  urlPlaceholder,
  saveLabel,
  cancelLabel,
  onChangeUrl,
  onChangeTitle,
  onChangeDescription,
  onSave,
  onClose,
}: ResourceMetaModalProps) {
  return (
    <AppModal visible={visible} animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.scrim} onPress={onClose}>
        <Pressable style={styles.sheet} onPress={() => undefined}>
          <Text style={styles.heading}>{heading}</Text>
          {preview ? <Text style={styles.preview}>{preview}</Text> : null}
          {showUrl ? (
            <View style={styles.field}>
              <Text style={styles.label}>{urlLabel}</Text>
              <TextInput
                value={url}
                onChangeText={onChangeUrl}
                placeholder={urlPlaceholder}
                placeholderTextColor={MUTED}
                style={styles.input}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="url"
              />
            </View>
          ) : null}
          <View style={styles.field}>
            <Text style={styles.label}>{titleLabel}</Text>
            <TextInput
              value={title}
              onChangeText={onChangeTitle}
              placeholder={titlePlaceholder}
              placeholderTextColor={MUTED}
              style={styles.input}
            />
          </View>
          <View style={styles.field}>
            <Text style={styles.label}>{descriptionLabel}</Text>
            <TextInput
              value={description}
              onChangeText={onChangeDescription}
              placeholder={descriptionPlaceholder}
              placeholderTextColor={MUTED}
              style={[styles.input, styles.multiline]}
              multiline
            />
          </View>
          {error ? <Text style={styles.error}>{error}</Text> : null}
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
    borderRadius: 16,
    padding: 18,
    gap: 12,
  },
  heading: { color: TEAL_DARK, fontFamily: fonts.bodyMedium, fontSize: 17, fontWeight: '700' },
  preview: { color: MUTED, fontFamily: fonts.body, fontSize: 13 },
  field: { gap: 6 },
  label: { color: TEAL_DARK, fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '600' },
  input: {
    borderWidth: 1,
    borderColor: BORDER,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontFamily: fonts.body,
    fontSize: 15,
    color: TEAL_DARK,
  },
  multiline: { minHeight: 72, textAlignVertical: 'top' },
  error: { color: '#DC2626', fontFamily: fonts.body, fontSize: 13 },
  row: { flexDirection: 'row', gap: 8, justifyContent: 'flex-end' },
  ghost: { paddingHorizontal: 14, paddingVertical: 10 },
  ghostText: { color: MUTED, fontFamily: fonts.bodyMedium, fontSize: 15 },
  save: {
    backgroundColor: TEAL,
    borderRadius: 8,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  saveText: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
});
