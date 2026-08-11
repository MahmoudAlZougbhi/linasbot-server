import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { EmptyState } from '../../components/EmptyState';
import { colors, fonts, radii, spacing } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';

const UsageSchema = z.object({ success: z.literal(true) }).passthrough();

type Props = Record<string, never>;

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

export function UsageScreen(_props: Props = {}) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const res = await apiFetch('/api/mobile/usage', { schema: UsageSchema });
        setData(res as Record<string, unknown>);
        setError(null);
      } catch {
        setError('Could not load usage. Please try again.');
        setData(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const bars = useMemo(() => {
    if (!data) return [];
    const candidates = [
      {
        label: 'Messages',
        used: num(data.messages_used) ?? num(data.used) ?? num(data.usage),
        max: num(data.messages_limit) ?? num(data.limit) ?? num(data.included),
      },
      {
        label: 'DM replies',
        used: num(data.dm_used) ?? num(data.dm_replies_used),
        max: num(data.dm_limit) ?? num(data.included_dm_replies),
      },
      {
        label: 'Credits',
        used: num(data.credits_used),
        max: num(data.credits_limit) ?? num(data.credits),
      },
    ];
    return candidates.filter((c) => c.used != null || c.max != null);
  }, [data]);

  return (
    <ScreenChrome title="Usage & Credits" subtitle="Included period balance">
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <ScrollView contentContainerStyle={styles.list}>
        {bars.map((bar) => {
          const used = bar.used ?? 0;
          const max = bar.max ?? 0;
          const pct = max > 0 ? Math.min(1, used / max) : 0;
          return (
            <View key={bar.label} style={styles.card}>
              <Text style={styles.label}>{bar.label}</Text>
              <Text style={styles.nums}>
                {used.toLocaleString()} / {max > 0 ? max.toLocaleString() : '—'}
                {max > 0 ? ` (${Math.round(pct * 100)}%)` : ''}
              </Text>
              <View style={styles.track}>
                <View style={[styles.fill, { width: `${pct * 100}%` }]} />
              </View>
            </View>
          );
        })}
        {__DEV__ && data ? (
          <Text style={styles.mono}>{JSON.stringify(data, null, 2)}</Text>
        ) : !loading && bars.length === 0 ? (
          <EmptyState title="No usage data yet" body="Check back after you start using Linas AI." />
        ) : null}
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
    borderWidth: 1,
    borderColor: colors.border,
  },
  label: { color: colors.textDim, fontFamily: fonts.bodyMedium, fontSize: 12 },
  nums: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 18, marginTop: 6 },
  track: {
    marginTop: 12,
    height: 8,
    borderRadius: 999,
    backgroundColor: colors.progressTrack,
    overflow: 'hidden',
  },
  fill: { height: '100%', backgroundColor: colors.accent, borderRadius: 999 },
  mono: { color: colors.textMuted, fontFamily: 'Courier', fontSize: 11, lineHeight: 16 },
  error: { color: colors.danger, marginBottom: spacing.md, fontFamily: fonts.body },
});
