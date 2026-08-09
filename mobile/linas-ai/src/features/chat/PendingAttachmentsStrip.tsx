import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { fonts, radii, spacing, useTheme } from '../../theme';
import { isImageMime, type PendingFile } from './v2/pickAttachment';

type Props = {
  files: PendingFile[];
  onRemove: (id: string) => void;
};

export function PendingAttachmentsStrip({ files, onRemove }: Props) {
  const { colors } = useTheme();
  if (!files.length) return null;

  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.row}
      style={styles.wrap}
      keyboardShouldPersistTaps="handled"
    >
      {files.map((f) => (
        <View key={f.id} style={[styles.thumbWrap, { borderColor: colors.border, backgroundColor: colors.surface }]}>
          {isImageMime(f.mimeType) ? (
            <Image source={{ uri: f.uri }} style={styles.thumb} accessibilityLabel={f.name} />
          ) : (
            <View style={[styles.doc, { backgroundColor: colors.bgElevated }]}>
              <Text style={[styles.docLabel, { color: colors.textMuted }]} numberOfLines={2}>
                {f.name}
              </Text>
            </View>
          )}
          <Pressable
            style={[styles.remove, { backgroundColor: colors.overlay }]}
            onPress={() => onRemove(f.id)}
            hitSlop={8}
            accessibilityLabel={`Remove ${f.name}`}
          >
            <Text style={[styles.removeText, { color: colors.onAccent }]}>×</Text>
          </Pressable>
        </View>
      ))}
    </ScrollView>
  );
}

const THUMB = 56;

const styles = StyleSheet.create({
  wrap: {
    maxHeight: THUMB + spacing.md,
    marginBottom: spacing.sm,
  },
  row: {
    paddingHorizontal: spacing.md,
    gap: spacing.sm,
    alignItems: 'center',
  },
  thumbWrap: {
    width: THUMB,
    height: THUMB,
    borderRadius: radii.md,
    borderWidth: 1,
    overflow: 'hidden',
  },
  thumb: { width: '100%', height: '100%' },
  doc: {
    flex: 1,
    padding: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  docLabel: { fontFamily: fonts.body, fontSize: 9, textAlign: 'center' },
  remove: {
    position: 'absolute',
    top: 2,
    right: 2,
    width: 20,
    height: 20,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  removeText: { fontSize: 14, fontWeight: '700', lineHeight: 16 },
});
