import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { fonts, radii, spacing, useTheme } from '../../theme';

export type PickOption = { id: string; label: string };

type Props = {
  visible: boolean;
  title: string;
  options: PickOption[];
  selectedId?: string | null;
  onPick: (id: string) => void;
  onClose: () => void;
};

export function RequestPickSheet({ visible, title, options, selectedId, onPick, onClose }: Props) {
  const { colors } = useTheme();
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable
          style={[styles.sheet, { backgroundColor: colors.surface, borderColor: colors.border }]}
          onPress={(e) => e.stopPropagation()}
        >
          <View style={[styles.handle, { backgroundColor: colors.border }]} />
          <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
          <ScrollView style={styles.list}>
            {options.map((opt) => {
              const active = selectedId === opt.id;
              return (
                <Pressable
                  key={opt.id}
                  onPress={() => {
                    onPick(opt.id);
                    onClose();
                  }}
                  style={[styles.row, { borderBottomColor: colors.borderSoft }]}
                  accessibilityRole="button"
                  accessibilityState={{ selected: active }}
                >
                  <Text style={[styles.label, { color: active ? colors.accent : colors.text }]}>
                    {opt.label}
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' },
  sheet: {
    borderTopLeftRadius: radii.xl,
    borderTopRightRadius: radii.xl,
    borderWidth: 1,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xxl,
    maxHeight: '70%',
  },
  handle: { width: 36, height: 4, borderRadius: 2, alignSelf: 'center', marginTop: 10, marginBottom: 12 },
  title: { fontFamily: fonts.bodyMedium, fontSize: 17, fontWeight: '700', marginBottom: spacing.sm },
  list: { maxHeight: 320 },
  row: { paddingVertical: 14, borderBottomWidth: StyleSheet.hairlineWidth },
  label: { fontFamily: fonts.bodyMedium, fontSize: 16 },
});
