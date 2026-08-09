import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { EmptyState } from '../../components/EmptyState';
import { StatusChip } from '../../components/StatusChip';
import { colors, fonts, radii, spacing } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';

const MetricsSchema = z
  .object({
    success: z.boolean(),
  })
  .passthrough();

const UsageSchema = z
  .object({
    success: z.literal(true),
    credit_balance: z.unknown().optional(),
  })
  .passthrough();

type Props = { onBack: () => void; isPlatformOwner: boolean };

export function DashboardScreen({ onBack, isPlatformOwner }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [usageText, setUsageText] = useState<string | null>(null);
  const [metricsText, setMetricsText] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const usage = await apiFetch('/api/mobile/usage', { schema: UsageSchema });
        setUsageText(JSON.stringify(usage.credit_balance ?? usage, null, 2));
        if (isPlatformOwner) {
          try {
            const metrics = await apiFetch('/api/platform/metrics', { schema: MetricsSchema });
            setMetricsText(JSON.stringify(metrics, null, 2));
          } catch {
            setMetricsText(null);
          }
        }
      } catch {
        setError('Dashboard data unavailable. APIs may not be deployed yet.');
      } finally {
        setLoading(false);
      }
    })();
  }, [isPlatformOwner]);

  return (
    <ScreenChrome
      title="Dashboard"
      subtitle="Truthful metrics from usage and platform APIs"
      onBack={onBack}
    >
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <ScrollView contentContainerStyle={styles.list}>
        <View style={styles.card}>
          <View style={styles.cardHead}>
            <Text style={styles.cardTitle}>Usage & credits</Text>
            <StatusChip label={usageText ? 'Loaded' : 'Empty'} tone={usageText ? 'ok' : 'soon'} />
          </View>
          {usageText ? (
            <Text style={styles.mono}>{usageText}</Text>
          ) : (
            <EmptyState title="No usage payload" body="Try again after entitlements APIs are live." />
          )}
        </View>
        <View style={styles.card}>
          <View style={styles.cardHead}>
            <Text style={styles.cardTitle}>Platform metrics</Text>
            <StatusChip
              label={isPlatformOwner ? (metricsText ? 'Owner' : 'Unavailable') : 'Owner only'}
              tone={metricsText ? 'ok' : 'soon'}
            />
          </View>
          {metricsText ? (
            <Text style={styles.mono}>{metricsText}</Text>
          ) : (
            <EmptyState
              title={isPlatformOwner ? 'Metrics unavailable' : 'Platform owner only'}
              body="Owner Control Center metrics require platform_owner role."
            />
          )}
        </View>
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
  cardHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  cardTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 16 },
  mono: { color: colors.textMuted, fontFamily: 'Courier', fontSize: 12, lineHeight: 18 },
  error: { color: colors.danger, marginBottom: spacing.md, fontFamily: fonts.body },
});
