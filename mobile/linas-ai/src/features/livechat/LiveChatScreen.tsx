import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { EmptyState } from '../../components/EmptyState';
import { StatusChip } from '../../components/StatusChip';
import { colors, fonts, radii, spacing } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';

const StatusSchema = z
  .object({
    success: z.boolean(),
    index_count: z.number().optional(),
    users_count: z.number().optional(),
    suggestion: z.string().nullable().optional(),
    error: z.string().optional(),
  })
  .passthrough();

type Props = { onBack: () => void };

export function LiveChatScreen({ onBack }: Props) {
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<z.infer<typeof StatusSchema> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const data = await apiFetch('/api/live-chat/status', { schema: StatusSchema });
        setStatus(data);
        setError(null);
      } catch {
        setError('Live Chat ops API not reachable from this session.');
        setStatus(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <ScreenChrome
      title="Live Chat"
      subtitle="Operator inbox — truthful status from existing APIs"
      onBack={onBack}
    >
      <View style={styles.banner}>
        <StatusChip label="Ops surface" tone="warn" />
        <Text style={styles.bannerText}>
          Full operator takeover UI remains on the dashboard. This mobile view shows availability
          and index health — not a fake chat console.
        </Text>
      </View>
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <ScrollView>
        {status?.success ? (
          <View style={styles.card}>
            <Text style={styles.row}>Index conversations: {status.index_count ?? 0}</Text>
            <Text style={styles.row}>Users: {status.users_count ?? 0}</Text>
            {status.suggestion ? <Text style={styles.hint}>{status.suggestion}</Text> : null}
          </View>
        ) : !loading ? (
          <EmptyState
            title="Live Chat unavailable here"
            body="Use the dashboard Live Chat for full operator workflows, or retry after API deploy."
          />
        ) : null}
      </ScrollView>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.lg,
    gap: spacing.sm,
  },
  bannerText: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 13, lineHeight: 19 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    gap: 8,
  },
  row: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 15 },
  hint: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 13, marginTop: 8 },
  error: { color: colors.danger, marginBottom: spacing.md, fontFamily: fonts.body },
});
