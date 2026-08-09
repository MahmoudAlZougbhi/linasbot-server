import { useState } from 'react';
import { Image, Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { radii, spacing, useTheme } from '../../theme';

type Props = {
  uris: string[];
};

export function MessageImageThumbs({ uris }: Props) {
  const { colors } = useTheme();
  const [previewUri, setPreviewUri] = useState<string | null>(null);
  if (!uris.length) return null;

  return (
    <>
      <View style={styles.row}>
        {uris.map((uri) => (
          <Pressable
            key={uri}
            onPress={() => setPreviewUri(uri)}
            style={[styles.thumbWrap, { borderColor: colors.borderSoft }]}
            accessibilityLabel="Open image"
          >
            <Image source={{ uri }} style={styles.thumb} />
          </Pressable>
        ))}
      </View>
      <Modal visible={Boolean(previewUri)} transparent animationType="fade" onRequestClose={() => setPreviewUri(null)}>
        <Pressable style={[styles.lightbox, { backgroundColor: colors.overlay }]} onPress={() => setPreviewUri(null)}>
          {previewUri ? (
            <Image source={{ uri: previewUri }} style={styles.full} resizeMode="contain" />
          ) : null}
          <Text style={[styles.closeHint, { color: colors.onAccent }]}>Tap to close</Text>
        </Pressable>
      </Modal>
    </>
  );
}

const THUMB = 64;

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  thumbWrap: {
    width: THUMB,
    height: THUMB,
    borderRadius: radii.md,
    overflow: 'hidden',
    borderWidth: 1,
  },
  thumb: { width: '100%', height: '100%' },
  lightbox: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  full: { width: '100%', height: '80%' },
  closeHint: { marginTop: spacing.md, fontSize: 13 },
});
