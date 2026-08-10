import { StyleSheet, Text, View } from 'react-native';

import { fonts, useTheme } from '../../theme';

/** Optional workspace pill under header (design: Sample Studio chip). */
export function ChatWorkspaceChip({ label }: { label: string }) {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap}>
      <View
        style={[styles.chip, { backgroundColor: colors.surfaceAlt, borderColor: colors.borderSoft }]}
      >
        <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 12 }}>{label}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: 'center', paddingBottom: 6, paddingTop: 2 },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 999,
    borderWidth: StyleSheet.hairlineWidth,
  },
});
