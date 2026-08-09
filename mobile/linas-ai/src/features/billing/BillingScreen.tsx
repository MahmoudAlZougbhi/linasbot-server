import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { EmptyState } from '../../components/EmptyState';
import { StatusChip } from '../../components/StatusChip';
import { colors, fonts, radii, spacing } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import { formatUsd, PLAN_CARDS } from './planCatalog';

const EntitlementsSchema = z.object({ success: z.boolean() }).passthrough();

type Props = { onBack: () => void };

export function BillingScreen({ onBack }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<string | null>(null);
  const [yearly, setYearly] = useState(false);
  const [raw, setRaw] = useState('');

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const data = await apiFetch('/api/entitlements/me', { schema: EntitlementsSchema });
        const record = data as Record<string, unknown>;
        const p =
          (typeof record.plan === 'string' && record.plan) ||
          (typeof record.plan_id === 'string' && record.plan_id) ||
          (typeof record.tier === 'string' && record.tier) ||
          null;
        setPlan(p);
        setRaw(JSON.stringify(data, null, 2));
        setError(null);
      } catch {
        setError('Entitlements unavailable. Store IAP may still be pending.');
        setRaw('');
        setPlan(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <ScreenChrome
      title="Subscription"
      subtitle="List prices + server entitlements (no fake IAP)"
      onBack={onBack}
    >
      <View style={styles.toggleRow}>
        <Pressable
          style={[styles.toggle, !yearly && styles.toggleOn]}
          onPress={() => setYearly(false)}
        >
          <Text style={styles.toggleText}>Monthly</Text>
        </Pressable>
        <Pressable
          style={[styles.toggle, yearly && styles.toggleOn]}
          onPress={() => setYearly(true)}
        >
          <Text style={styles.toggleText}>Yearly (Save 20%)</Text>
        </Pressable>
      </View>

      <View style={styles.banner}>
        <StatusChip label="IAP external" tone="soon" />
        <Text style={styles.bannerText}>
          Prices match product catalog. Purchase happens in App Store / Play — this screen shows
          entitlements only.
        </Text>
        {plan ? <Text style={styles.current}>Current entitlement plan: {plan}</Text> : null}
      </View>

      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}

      <ScrollView contentContainerStyle={styles.list}>
        {PLAN_CARDS.map((card) => {
          const monthly = card.priceMonthly;
          const shown = yearly ? monthly * 12 * 0.8 : monthly;
          const period = yearly ? '/yr' : '/mo';
          const active = plan?.toLowerCase() === card.id;
          return (
            <View key={card.id} style={[styles.card, active && styles.cardActive]}>
              <View style={styles.cardHead}>
                <Text style={styles.name}>{card.name}</Text>
                {active ? <StatusChip label="current" tone="ok" /> : null}
              </View>
              <Text style={styles.price}>
                {formatUsd(Number(shown.toFixed(2)))}
                <Text style={styles.period}>{period}</Text>
              </Text>
              <Text style={styles.blurb}>{card.blurb}</Text>
              {card.features.map((f) => (
                <Text key={f} style={styles.feature}>
                  · {f}
                </Text>
              ))}
            </View>
          );
        })}
        {raw ? (
          <View style={styles.rawBox}>
            <Text style={styles.rawLabel}>Entitlements payload</Text>
            <Text style={styles.mono}>{raw}</Text>
          </View>
        ) : !loading && !error ? (
          <EmptyState title="No entitlement data" body="Sign in after API deploy." />
        ) : null}
      </ScrollView>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  toggleRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: spacing.md,
  },
  toggle: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
  },
  toggleOn: { backgroundColor: colors.accentSoft, borderColor: colors.accent },
  toggleText: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 13 },
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
  current: { color: colors.accentDeep, fontFamily: fonts.bodyMedium, fontSize: 13 },
  list: { paddingBottom: 40, gap: spacing.md },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  cardActive: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
  cardHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  name: { color: colors.accentDeep, fontFamily: fonts.display, fontSize: 20 },
  price: { color: colors.text, fontFamily: fonts.display, fontSize: 28, marginTop: 6 },
  period: { fontSize: 14, color: colors.textMuted, fontFamily: fonts.body },
  blurb: { color: colors.textMuted, fontFamily: fonts.body, marginTop: 6, marginBottom: 8 },
  feature: { color: colors.text, fontFamily: fonts.body, fontSize: 13, marginTop: 2 },
  rawBox: { marginTop: spacing.md },
  rawLabel: { color: colors.textDim, fontFamily: fonts.bodyMedium, marginBottom: 6, fontSize: 12 },
  mono: { color: colors.textMuted, fontFamily: 'Courier', fontSize: 11, lineHeight: 16 },
  error: { color: colors.danger, marginBottom: spacing.md, fontFamily: fonts.body },
});
