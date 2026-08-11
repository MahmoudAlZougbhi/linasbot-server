import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { z } from 'zod';

import { ApiError, apiFetch } from '../../api/client';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing } from '../../theme';

export const WhatsAppStatusSchema = z.object({
  success: z.literal(true),
  platform: z.literal('whatsapp').optional(),
  lifecycle_status: z.string(),
  connectable: z.boolean(),
  coming_soon: z.boolean().optional(),
  public_availability: z.boolean().optional(),
  pilot_entitled: z.boolean().optional(),
  blocker_code: z.string().nullable().optional(),
  connection: z
    .object({
      connection_id: z.string(),
      lifecycle_status: z.string(),
      display_phone_last4: z.string().optional(),
      verified_name: z.string().optional(),
      ai_eligible: z.boolean().optional(),
      ai_default_enabled: z.boolean().optional(),
      health_status: z.string().optional(),
      coexistence_mode: z.string().optional(),
      rollout_blocked_reason: z.string().nullable().optional(),
    })
    .nullable()
    .optional(),
  flags: z
    .object({
      connection_ui_enabled: z.boolean(),
      ai_replies_enabled: z.boolean().optional(),
      embedded_signup_config_configured: z.boolean().optional(),
    })
    .optional(),
});

export type WhatsAppCloudStatus = z.infer<typeof WhatsAppStatusSchema>;

const StartSchema = z.object({
  success: z.literal(true),
  authorization_url: z.string().url(),
  correlation_id: z.string().optional(),
});

type Status = WhatsAppCloudStatus;

type Props = {
  status: Status | null;
  loading?: boolean;
  busy?: boolean;
  onRefresh: () => void;
  onConnect: () => void;
  onEnableAi?: (connectionId: string) => void;
  onDisableAi?: (connectionId: string) => void;
};

export async function fetchWhatsAppCloudStatus(): Promise<Status> {
  return apiFetch('/api/whatsapp/cloud/status', { schema: WhatsAppStatusSchema });
}

export async function startWhatsAppCloudConnect(): Promise<void> {
  const { Linking } = await import('react-native');
  const started = await apiFetch('/api/whatsapp/cloud/connect/start', {
    method: 'POST',
    body: JSON.stringify({ return_surface: 'mobile' }),
    schema: StartSchema,
  });
  await Linking.openURL(started.authorization_url);
}

export function WhatsAppCloudCard({
  status,
  loading,
  busy,
  onRefresh,
  onConnect,
  onEnableAi,
  onDisableAi,
}: Props) {
  const { tr } = useI18n();
  const lifecycle = status?.lifecycle_status || 'disconnected';
  const connected = lifecycle === 'connected';
  const connectable = status?.connectable === true;
  const comingSoon = status?.coming_soon === true || (!connectable && !connected);
  const conn = status?.connection;
  const last4 = conn?.display_phone_last4 ? `••••${conn.display_phone_last4}` : null;

  let stateLabel = tr('waStateDisconnected');
  if (comingSoon && !connected) stateLabel = tr('waStateUnavailable');
  else if (lifecycle === 'awaiting_meta' || lifecycle === 'starting') stateLabel = tr('waStateAwaitingMeta');
  else if (lifecycle === 'provisioning' || lifecycle === 'syncing_history') stateLabel = tr('waStateProvisioning');
  else if (lifecycle === 'needs_attention') stateLabel = tr('waStateNeedsAttention');
  else if (lifecycle === 'failed') stateLabel = tr('waStateFailed');
  else if (connected) stateLabel = tr('waStateConnected');

  return (
    <View style={styles.card} accessibilityRole="summary">
      <Text style={styles.title}>{tr('platformWhatsApp')}</Text>
      <Text style={styles.sub}>{tr('waCoexistenceHint')}</Text>
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      <Text style={styles.state}>{stateLabel}</Text>
      {last4 ? (
        <Text style={styles.meta}>
          {tr('waNumberLabel')}: {last4}
          {conn?.verified_name ? ` · ${conn.verified_name}` : ''}
        </Text>
      ) : null}
      {conn?.coexistence_mode ? <Text style={styles.meta}>{tr('waCoexistenceOn')}</Text> : null}
      {connected ? (
        <Text style={styles.meta}>
          {tr('waAiLabel')}:{' '}
          {conn?.ai_eligible && conn?.ai_default_enabled ? tr('waAiOn') : tr('waAiPausedOrOff')}
        </Text>
      ) : null}
      {status?.blocker_code ? <Text style={styles.warn}>{status.blocker_code}</Text> : null}
      {conn?.rollout_blocked_reason ? <Text style={styles.warn}>{conn.rollout_blocked_reason}</Text> : null}
      {!connected && connectable ? (
        <PrimaryButton label={tr('waConnect')} onPress={onConnect} loading={busy} />
      ) : null}
      {connected && conn?.connection_id && onEnableAi && !conn.ai_default_enabled ? (
        <PrimaryButton label={tr('waEnableAi')} onPress={() => onEnableAi(conn.connection_id)} variant="ghost" />
      ) : null}
      {connected && conn?.connection_id && onDisableAi && conn.ai_default_enabled ? (
        <PrimaryButton label={tr('waDisableAi')} onPress={() => onDisableAi(conn.connection_id)} variant="ghost" />
      ) : null}
      <PrimaryButton label={tr('refreshConnectionStatus')} onPress={onRefresh} variant="ghost" loading={loading} />
    </View>
  );
}

export function isWhatsAppApiError(err: unknown): err is ApiError {
  return err instanceof ApiError;
}

const styles = StyleSheet.create({
  card: {
    gap: spacing.sm,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  title: { color: colors.text, fontFamily: fonts.display, fontSize: 18 },
  sub: { color: colors.textMuted, fontSize: 13, lineHeight: 18 },
  state: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 15 },
  meta: { color: colors.textMuted, fontSize: 13 },
  warn: { color: colors.danger, fontSize: 12 },
});
