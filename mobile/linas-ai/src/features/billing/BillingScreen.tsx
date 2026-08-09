import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { EmptyState } from '../../components/EmptyState';
import { StatusChip } from '../../components/StatusChip';
import { colors, fonts, radii, spacing } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';

const EntitlementsSchema = z.object({ success: z.boolean() }).passthrough();

type Props = { onBack: () => void };

export function BillingScreen({ onBack }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<string>('');

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const data = await apiFetch('/api/entitlements/me', { schema: EntitlementsSchema });
        setPayload(JSON.stringify(data, null, 2));
        setError(null);
      } catch {
        setError('Entitlements unavailable. Store IAP / billing may still be pending.');
        setPayload('');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <ScreenChrome
      title="Billing"
      subtitle="Subscription entitlements from Linas API"
      onBack={onBack}
    >
      <View style={styles.banner}>
        <StatusChip label="IAP external" tone="soon" />
        <Text style={styles.bannerText}>
          Apple/Google subscriptions are provisioned outside this UI. This screen shows server
          entitlements only — no fake subscribe buttons.
        </Text>
      </View>
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <ScrollView>
        {payload ? (
          <Text style={styles.mono}>{payload}</Text>
        ) : !loading ? (
          <EmptyState title="No entitlement data" body="Sign in after Phase 2 API deploy." />
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
  mono: { color: colors.textMuted, fontFamily: 'Courier', fontSize: 12, lineHeight: 18 },
  error: { color: colors.danger, marginBottom: spacing.md, fontFamily: fonts.body },
});
