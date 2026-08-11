import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { z } from 'zod';

import { ApiError, apiFetch } from '../../api/client';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';

const PilotListSchema = z.object({
  success: z.literal(true),
  public_availability: z.boolean(),
  require_pilot_entitlement: z.boolean(),
  pilots: z.array(
    z.object({
      tenant_id: z.string(),
      status: z.string(),
      reason: z.string(),
      granted_by_user_id: z.string().optional(),
      created_at: z.string().nullable().optional(),
      revoked_at: z.string().nullable().optional(),
    }),
  ),
});

type PilotRow = z.infer<typeof PilotListSchema>['pilots'][number];

/** Platform-owner WhatsApp pilot entitlement controls (ops-time tenant_id argument only). */
export function OwnerPortalScreen() {
  const { tr } = useI18n();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pilots, setPilots] = useState<PilotRow[]>([]);
  const [publicAvailability, setPublicAvailability] = useState(false);
  const [requirePilot, setRequirePilot] = useState(true);
  const [tenantId, setTenantId] = useState('');
  const [reason, setReason] = useState('Internal App Review / coexistence pilot');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch('/api/whatsapp/cloud/pilot/list', { schema: PilotListSchema });
      setPilots(data.pilots);
      setPublicAvailability(data.public_availability);
      setRequirePilot(data.require_pilot_entitlement);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError(tr('waOwnerPortalForbidden'));
      } else {
        setError(tr('integrationsLoadError'));
      }
    } finally {
      setLoading(false);
    }
  }, [tr]);

  useEffect(() => {
    void load();
  }, [load]);

  async function grant() {
    const tid = tenantId.trim().toLowerCase();
    const why = reason.trim();
    if (!tid || !why) {
      setError(tr('waGrantTenantReasonRequired'));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await apiFetch('/api/whatsapp/cloud/pilot/grant', {
        method: 'POST',
        body: JSON.stringify({ tenant_id: tid, reason: why }),
        schema: z.object({ success: z.literal(true), tenant_id: z.string(), status: z.string() }),
      });
      setNotice(`${tr('waPilotGranted')}: ${tid}`);
      setTenantId('');
      await load();
    } catch {
      setError(tr('integrationsActionError'));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(tid: string) {
    setBusy(true);
    setError(null);
    try {
      await apiFetch('/api/whatsapp/cloud/pilot/revoke', {
        method: 'POST',
        body: JSON.stringify({ tenant_id: tid }),
        schema: z.object({ success: z.literal(true), tenant_id: z.string(), status: z.string() }),
      });
      setNotice(`${tr('waPilotRevoked')}: ${tid}`);
      await load();
    } catch {
      setError(tr('integrationsActionError'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScreenChrome title={tr('waOwnerPortalTitle')} subtitle={tr('waOwnerPortalSub')}>
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {notice ? <Text style={styles.notice}>{notice}</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Text style={styles.meta}>
        {tr('waPublicAvailability')}: {publicAvailability ? tr('waOn') : tr('waOff')}
      </Text>
      <Text style={styles.meta}>
        {tr('waRequirePilot')}: {requirePilot ? tr('waOn') : tr('waOff')}
      </Text>
      <Text style={styles.hint}>{tr('waPhase2Hint')}</Text>

      <Text style={styles.section}>{tr('waGrantPilotTitle')}</Text>
      <TextInput
        style={styles.input}
        value={tenantId}
        onChangeText={setTenantId}
        placeholder={tr('waTenantIdPlaceholder')}
        placeholderTextColor={colors.textDim}
        autoCapitalize="none"
        autoCorrect={false}
      />
      <TextInput
        style={[styles.input, styles.multiline]}
        value={reason}
        onChangeText={setReason}
        placeholder={tr('waPilotReasonPlaceholder')}
        placeholderTextColor={colors.textDim}
        multiline
      />
      <PrimaryButton label={tr('waGrantPilot')} loading={busy} onPress={() => void grant()} />

      <Text style={styles.section}>{tr('waPilotListTitle')}</Text>
      <ScrollView contentContainerStyle={styles.list}>
        {pilots.length === 0 ? <Text style={styles.meta}>{tr('waNoPilots')}</Text> : null}
        {pilots.map((p) => (
          <View key={`${p.tenant_id}-${p.status}-${p.created_at || ''}`} style={styles.row}>
            <Text style={styles.rowTitle}>
              {p.tenant_id} · {p.status}
            </Text>
            <Text style={styles.meta}>{p.reason}</Text>
            {p.status === 'active' ? (
              <PrimaryButton
                label={tr('waRevokePilot')}
                variant="ghost"
                loading={busy}
                onPress={() => void revoke(p.tenant_id)}
              />
            ) : null}
          </View>
        ))}
      </ScrollView>
      <PrimaryButton label={tr('refreshConnectionStatus')} variant="ghost" loading={loading} onPress={() => void load()} />
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  notice: { color: colors.accent, marginBottom: spacing.sm, fontFamily: fonts.body },
  error: { color: colors.danger, marginBottom: spacing.sm, fontFamily: fonts.body },
  section: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 16, marginTop: spacing.lg },
  hint: { color: colors.textMuted, fontSize: 12, lineHeight: 17, marginBottom: spacing.sm },
  meta: { color: colors.textMuted, fontSize: 13, marginBottom: 4 },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: colors.text,
    fontFamily: fonts.body,
    fontSize: 14,
    marginBottom: spacing.sm,
  },
  multiline: { minHeight: 64, textAlignVertical: 'top' },
  list: { paddingBottom: 40, gap: spacing.sm },
  row: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    paddingVertical: spacing.sm,
    gap: 4,
  },
  rowTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 14 },
});
