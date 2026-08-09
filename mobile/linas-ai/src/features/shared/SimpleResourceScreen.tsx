import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { colors } from '../../theme/colors';

type Props = {
  title: string;
  path: string;
  onBack: () => void;
};

const LooseSchema = z.object({ success: z.boolean() }).passthrough();

export function SimpleResourceScreen({ title, path, onBack }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await apiFetch(path, { schema: LooseSchema });
        if (!cancelled) {
          setPayload(JSON.stringify(data, null, 2));
        }
      } catch {
        if (!cancelled) {
          setError('Failed to load. Pull back and open again to retry.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [path]);

  return (
    <View style={styles.root}>
      <Pressable onPress={onBack} style={styles.back}>
        <Text style={styles.link}>Back</Text>
      </Pressable>
      <Text style={styles.title}>{title}</Text>
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <ScrollView>
        <Text style={styles.mono}>{payload}</Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg, paddingTop: 56, paddingHorizontal: 16 },
  back: { marginBottom: 8 },
  link: { color: colors.accent },
  title: { color: colors.text, fontSize: 24, fontWeight: '700', marginBottom: 16 },
  mono: { color: colors.textMuted, fontFamily: 'Courier', fontSize: 12, lineHeight: 18 },
  error: { color: colors.danger, marginBottom: 12 },
});
