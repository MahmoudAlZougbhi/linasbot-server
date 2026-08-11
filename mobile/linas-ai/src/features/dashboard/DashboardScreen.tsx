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
    credits_used: z.number().optional(),
    credits_limit: z.number().optional(),
    credits: z.number().optional(),
    plan_id: z.string().optional(),
  })
  .passthrough();

type Props = { isPlatformOwner: boolean };

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

export function DashboardScreen({ isPlatformOwner }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [usageSummary, setUsageSummary] = useState<string | null>(null);
  const [hasMetrics, setHasMetrics] = useState(false);
  const [usageText, setUsageText] = useState<string | null>(null);
  const [metricsText, setMetricsText] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const usage = await apiFetch('/api/mobile/usage', { schema: UsageSchema });
        const used = num(usage.credits_used);
        const limit = num(usage.credits_limit) ?? num(usage.credits);
        const plan = typeof usage.plan_id === 'string' ? usage.plan_id : null;
        if (used != null || limit != null) {
          const usedLabel = (used ?? 0).toLocaleString();
          const limitLabel = limit != null && limit > 0 ? limit.toLocaleString() : '—';
          const planLabel = plan && plan !== 'none' ? ` · ${plan}` : '';
          setUsageSummary(`${usedLabel} / ${limitLabel} credits used${planLabel}`);
        } else if (usage.credit_balance != null) {
          setUsageSummary(`Available balance: ${String(usage.credit_balance)}`);
        } else {
          setUsageSummary(null);
        }
        if (__DEV__) {
          setUsageText(JSON.stringify(usage, null, 2));
        } else {
          setUsageText(null);
        }
        if (isPlatformOwner) {
          try {
            const metrics = await apiFetch('/api/platform/metrics', { schema: MetricsSchema });
            setHasMetrics(true);
            if (__DEV__) {
              setMetricsText(JSON.stringify(metrics, null, 2));
            } else {
              setMetricsText(null);
            }
          } catch {
            setHasMetrics(false);
            setMetricsText(null);
          }
        }
      } catch {
        setError('Something went wrong loading the dashboard. Please try again.');
        setUsageSummary(null);
      } finally {
        setLoading(false);
      }
    })();
  }, [isPlatformOwner]);

  return (
    <ScreenChrome title="Dashboard" subtitle="Usage and workspace health">
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <ScrollView contentContainerStyle={styles.list}>
        <View style={styles.card}>
          <View style={styles.cardHead}>
            <Text style={styles.cardTitle}>Usage & credits</Text>
            <StatusChip label={usageSummary ? 'Ready' : 'Empty'} tone={usageSummary ? 'ok' : 'soon'} />
          </View>
          {usageSummary ? (
            <Text style={styles.body}>{usageSummary}</Text>
          ) : (
            <EmptyState
              title="No usage data yet"
              body="Check back after you start using Linas AI, or try again later."
            />
          )}
          {__DEV__ && usageText ? <Text style={styles.mono}>{usageText}</Text> : null}
        </View>
        <View style={styles.card}>
          <View style={styles.cardHead}>
            <Text style={styles.cardTitle}>Platform metrics</Text>
            <StatusChip
              label={isPlatformOwner ? (hasMetrics ? 'Ready' : 'Unavailable') : 'Owner only'}
              tone={hasMetrics ? 'ok' : 'soon'}
            />
          </View>
          {hasMetrics ? (
            <Text style={styles.body}>Platform metrics loaded for your owner workspace.</Text>
          ) : (
            <EmptyState
              title={isPlatformOwner ? 'Metrics unavailable' : 'Owner access only'}
              body={
                isPlatformOwner
                  ? 'Something went wrong loading metrics. Please try again.'
                  : 'Platform metrics are only available to workspace owners.'
              }
            />
          )}
          {__DEV__ && metricsText ? <Text style={styles.mono}>{metricsText}</Text> : null}
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
  body: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 14, lineHeight: 20 },
  mono: { color: colors.textMuted, fontFamily: 'Courier', fontSize: 12, lineHeight: 18, marginTop: 8 },
  error: { color: colors.danger, marginBottom: spacing.md, fontFamily: fonts.body },
});
