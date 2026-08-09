import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { colors, fonts, spacing } from '../../theme';
import { CREATE_POST_TASKS, type CreatePostTaskId } from './createPostTasks';

type Props = {
  selected: CreatePostTaskId;
  onSelect: (id: CreatePostTaskId) => void;
  onDismiss: () => void;
};

export function CreatePostTaskChips({ selected, onSelect, onDismiss }: Props) {
  return (
    <View style={styles.wrap}>
      <View style={styles.header}>
        <Text style={styles.title}>Create Post</Text>
        <Pressable onPress={onDismiss} hitSlop={8}>
          <Text style={styles.dismiss}>Done</Text>
        </Pressable>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.row}>
        {CREATE_POST_TASKS.map((task) => (
          <Pressable
            key={task.id}
            style={[
              styles.chip,
              selected === task.id && styles.chipOn,
              task.disabled && styles.chipOff,
            ]}
            disabled={task.disabled}
            onPress={() => onSelect(task.id)}
          >
            <Text style={[styles.chipText, selected === task.id && styles.chipTextOn]}>
              {task.label}
            </Text>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.sm,
    gap: 6,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  title: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 13 },
  dismiss: { color: colors.accent, fontFamily: fonts.bodyMedium, fontSize: 13 },
  row: { gap: 8, paddingVertical: 2 },
  chip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.bgElevated,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  chipOn: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
  chipOff: { opacity: 0.45 },
  chipText: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 12 },
  chipTextOn: { color: colors.accentDeep },
});
