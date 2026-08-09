import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { colors } from '../../theme/colors';

const CapSchema = z
  .object({
    level: z.string().optional(),
    supported_in_code: z.boolean().optional(),
    live_verified: z.boolean().optional(),
    notes: z.string().optional(),
  })
  .passthrough();

const Schema = z.object({
  success: z.literal(true),
  integrations: z.array(
    z.object({
      platform: z.string(),
      label: z.string(),
      connected: z.boolean(),
      capabilities: z.record(z.string(), z.union([z.string(), CapSchema])),
    }),
  ),
});

type Props = { onBack: () => void };

function statusLabel(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  if (value && typeof value === 'object') {
    const cap = value as z.infer<typeof CapSchema>;
    if (cap.live_verified) {
      return 'live';
    }
    if (cap.level === 'connected') {
      return 'connected';
    }
    if (cap.level === 'needs_permission') {
      return 'needs permission';
    }
    if (cap.level === 'coming_later') {
      return 'coming later';
    }
    return cap.level ?? 'unavailable';
  }
  return 'unavailable';
}

export function IntegrationsScreen({ onBack }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<z.infer<typeof Schema>['integrations']>([]);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const data = await apiFetch('/api/mobile/integrations', { schema: Schema });
        setRows(data.integrations);
        setError(null);
      } catch {
        setError('Could not load integrations.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <View style={styles.root}>
      <Pressable onPress={onBack}>
        <Text style={styles.link}>Back</Text>
      </Pressable>
      <Text style={styles.title}>Integrations</Text>
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <ScrollView contentContainerStyle={styles.list}>
        {rows.map((row) => (
          <View key={row.platform} style={styles.card}>
            <Text style={styles.cardTitle}>
              {row.label} · {row.connected ? 'connected' : 'not connected'}
            </Text>
            {Object.entries(row.capabilities).map(([key, value]) => (
              <Text key={key} style={styles.cap}>
                {key}: {statusLabel(value)}
              </Text>
            ))}
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg, paddingTop: 56, paddingHorizontal: 16 },
  link: { color: colors.accent, marginBottom: 8 },
  title: { color: colors.text, fontSize: 28, fontWeight: '700', marginBottom: 16 },
  list: { paddingBottom: 40, gap: 12 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 14,
    padding: 16,
    borderColor: colors.border,
    borderWidth: 1,
  },
  cardTitle: { color: colors.text, fontWeight: '700', marginBottom: 8 },
  cap: { color: colors.textMuted, marginBottom: 4 },
  error: { color: colors.danger, marginBottom: 12 },
});
