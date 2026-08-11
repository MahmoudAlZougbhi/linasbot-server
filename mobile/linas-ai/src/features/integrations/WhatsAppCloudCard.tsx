import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing } from '../../theme';
import { WhatsAppCloudOpsPanel } from './WhatsAppCloudOpsPanel';
import {
  fetchWhatsAppCloudStatus,
  startWhatsAppCloudConnect,
  WhatsAppConnectError,
  type WhatsAppCloudStatus,
} from './whatsappCloudApi';

export type { WhatsAppCloudStatus };
export { fetchWhatsAppCloudStatus, startWhatsAppCloudConnect, WhatsAppConnectError };

type Props = {
  status: WhatsAppCloudStatus | null;
  loading?: boolean;
  busy?: boolean;
  onRefresh: () => void;
  onConnect: () => void;
  onEnableAi?: (connectionId: string) => void;
  onDisableAi?: (connectionId: string) => void;
  onBusyChange?: (busy: boolean) => void;
  onError?: (message: string) => void;
  onNotice?: (message: string) => void;
};

export function WhatsAppCloudCard({
  status,
  loading,
  busy,
  onRefresh,
  onConnect,
  onEnableAi,
  onDisableAi,
  onBusyChange,
  onError,
  onNotice,
}: Props) {
  const { tr } = useI18n();
  const lifecycle = status?.lifecycle_status || 'disconnected';
  const connected = lifecycle === 'connected';
  const connectable = status?.connectable === true;
  const awaitingMeta =
    status?.awaiting_meta_approval === true ||
    (!connectable && !connected && !status?.pilot_entitled && status?.public_availability !== true);
  const conn = status?.connection;
  const last4 = conn?.display_phone_last4 ? `••••${conn.display_phone_last4}` : null;

  let stateLabel = tr('waStateDisconnected');
  if (awaitingMeta && !connected) stateLabel = tr('waStateAwaitingMetaApproval');
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
      {awaitingMeta && !connected ? (
        <Text style={styles.warn}>
          {status?.blocker_message?.trim() || tr('waAwaitingMetaApprovalBody')}
        </Text>
      ) : null}
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
      {status?.blocker_code && !awaitingMeta ? (
        <Text style={styles.warn}>{status.blocker_code}</Text>
      ) : null}
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
      {connected && conn?.connection_id ? (
        <WhatsAppCloudOpsPanel
          connectionId={conn.connection_id}
          busy={busy}
          onBusyChange={onBusyChange}
          onError={onError}
          onNotice={onNotice}
        />
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
  warn: { color: colors.danger, fontSize: 12, lineHeight: 17 },
});
