import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { EmptyState } from '../../components/EmptyState';
import { StatusChip } from '../../components/StatusChip';
import { colors, fonts, radii, spacing } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';

const MetaSchema = z
  .object({
    success: z.literal(true),
    sections: z.array(z.string()).optional(),
    publish_enabled: z.boolean().optional(),
    tenant_runtime: z.string().optional(),
    has_published_content: z.boolean().optional(),
    runtime_mode: z.string().optional(),
  })
  .passthrough();

type Props = { onBack: () => void };

export function CmScreen({ onBack }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<z.infer<typeof MetaSchema> | null>(null);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const data = await apiFetch('/api/cm/meta', { schema: MetaSchema });
        setMeta(data);
        setError(null);
      } catch {
        setError('Could not load Content Management meta.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <ScreenChrome
      title="Content Management"
      subtitle="Published CM runtime — no legacy bridge"
      onBack={onBack}
    >
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <ScrollView contentContainerStyle={styles.list}>
        {meta ? (
          <>
            <View style={styles.card}>
              <View style={styles.head}>
                <Text style={styles.cardTitle}>Runtime</Text>
                <StatusChip
                  label={meta.tenant_runtime ?? meta.runtime_mode ?? 'unknown'}
                  tone={meta.has_published_content ? 'ok' : 'warn'}
                />
              </View>
              <Text style={styles.line}>
                Publish: {meta.publish_enabled ? 'enabled' : 'disabled / gated'}
              </Text>
              <Text style={styles.line}>
                Published content: {meta.has_published_content ? 'yes' : 'no'}
              </Text>
            </View>
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Sections</Text>
              {(meta.sections ?? []).map((s) => (
                <Text key={s} style={styles.section}>
                  {s}
                </Text>
              ))}
              {(meta.sections ?? []).length === 0 ? (
                <EmptyState title="No sections listed" />
              ) : null}
            </View>
            <Text style={styles.hint}>
              Edit drafts and publish from chat tools or the dashboard. Mobile shows truthful status
              only — legacy Testing Lab bridge stays disabled.
            </Text>
          </>
        ) : !loading ? (
          <EmptyState title="CM unavailable" body="Retry after API deploy." />
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
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  cardTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 16, marginBottom: 8 },
  line: { color: colors.textMuted, fontFamily: fonts.body, marginTop: 4 },
  section: {
    color: colors.text,
    fontFamily: fonts.body,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSoft,
  },
  hint: { color: colors.textDim, fontFamily: fonts.body, fontSize: 12, lineHeight: 18 },
  error: { color: colors.danger, marginBottom: spacing.md, fontFamily: fonts.body },
});
