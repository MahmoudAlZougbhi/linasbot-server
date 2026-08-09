import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { StatusChip } from '../../components/StatusChip';
import { colors, fonts, radii, spacing } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';

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

function capTone(value: unknown): 'ok' | 'warn' | 'soon' | 'neutral' {
  if (typeof value === 'string') {
    if (value === 'live' || value === 'connected') return 'ok';
    if (value.includes('coming')) return 'soon';
    return 'neutral';
  }
  if (value && typeof value === 'object') {
    const cap = value as z.infer<typeof CapSchema>;
    if (cap.live_verified) return 'ok';
    if (cap.level === 'needs_permission') return 'warn';
    if (cap.level === 'coming_later') return 'soon';
  }
  return 'neutral';
}

function statusLabel(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object') {
    const cap = value as z.infer<typeof CapSchema>;
    if (cap.live_verified) return 'live';
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
    <ScreenChrome
      title="Integrations"
      subtitle="Truthful Meta readiness — never fake connected"
      onBack={onBack}
    >
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <ScrollView contentContainerStyle={styles.list}>
        {rows.map((row) => (
          <View key={row.platform} style={styles.card}>
            <View style={styles.head}>
              <Text style={styles.cardTitle}>{row.label}</Text>
              <StatusChip
                label={row.connected ? 'Connected' : 'Not connected'}
                tone={row.connected ? 'ok' : 'soon'}
              />
            </View>
            {Object.entries(row.capabilities).map(([key, value]) => (
              <View key={key} style={styles.capRow}>
                <Text style={styles.capKey}>{key}</Text>
                <StatusChip label={statusLabel(value)} tone={capTone(value)} />
              </View>
            ))}
          </View>
        ))}
      </ScrollView>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: 40, gap: spacing.md },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    padding: spacing.lg,
    borderColor: colors.border,
    borderWidth: 1,
  },
  head: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  cardTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 17 },
  capRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: colors.borderSoft,
  },
  capKey: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 13, flex: 1 },
  error: { color: colors.danger, marginBottom: spacing.md, fontFamily: fonts.body },
});
