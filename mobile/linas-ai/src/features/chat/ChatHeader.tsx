import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, fonts, spacing } from '../../theme';

type Props = {
  title: string;
  onOpenHistory: () => void;
  onOpenControl: () => void;
};

export function ChatHeader({ title, onOpenHistory, onOpenControl }: Props) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.bar, { paddingTop: insets.top + 8 }]}>
      <Pressable onPress={onOpenHistory} hitSlop={12} style={styles.hit}>
        <Text style={styles.icon}>☰</Text>
      </Pressable>
      <View style={styles.center}>
        <Text style={styles.brand}>Linas AI</Text>
        <Text style={styles.title} numberOfLines={1}>
          {title}
        </Text>
      </View>
      <Pressable onPress={onOpenControl} hitSlop={12} style={styles.hit}>
        <Text style={styles.icon}>◎</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSoft,
    backgroundColor: colors.bgElevated,
  },
  hit: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  icon: { color: colors.accent, fontSize: 18, fontWeight: '700' },
  center: { flex: 1, alignItems: 'center', paddingHorizontal: 8 },
  brand: { color: colors.textDim, fontFamily: fonts.bodyMedium, fontSize: 11, letterSpacing: 1 },
  title: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 16, marginTop: 2 },
});
