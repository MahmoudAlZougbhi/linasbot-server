import { StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts } from '../../theme';
import { ChannelCapabilityToggles } from './ChannelCapabilityToggles';
import { IntegrationCardShell } from './IntegrationCardShell';
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
  busy?: boolean;
  onRefresh: () => void;
  onConnect: () => void;
  onOpenMenu?: () => void;
  onEnableAi?: (connectionId: string) => void;
  onDisableAi?: (connectionId: string) => void;
  onBusyChange?: (busy: boolean) => void;
  onError?: (message: string) => void;
  onNotice?: (message: string) => void;
};

export function whatsappCardSubtitle(status: WhatsAppCloudStatus | null, fallback: string): string {
  const conn = status?.connection;
  if (status?.lifecycle_status === 'connected' && conn) {
    if (conn.verified_name?.trim()) return conn.verified_name.trim();
    if (conn.display_phone_last4) return `••••${conn.display_phone_last4}`;
  }
  return fallback;
}

export function WhatsAppCloudCard({
  status,
  busy,
  onConnect,
  onOpenMenu,
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
  const subtitle = whatsappCardSubtitle(status, tr('integrationWhatsAppHandle'));
  const healthy = connected;
  const aiOn = Boolean(conn?.ai_default_enabled);

  return (
    <View accessibilityRole="summary" style={styles.wrap}>
      <IntegrationCardShell
        platform="whatsapp"
        title={tr('platformWhatsApp')}
        subtitle={subtitle}
        connected={connected}
        busy={busy}
        connectLabel={tr('connect')}
        connectedLabel={tr('connected')}
        notConnectedLabel={tr('notConnected')}
        comingSoonLabel={tr('comingSoon')}
        healthLabel={tr('integrationStatusConnected')}
        menuLabel={tr('disconnectAccount')}
        showConnect={!connected && connectable}
        showMenu={connected}
        showHealth={healthy}
        onConnect={onConnect}
        onMenu={onOpenMenu}
      >
        {!connected && connectable ? (
          <>
            <Text style={styles.hint}>{tr('waCoexistenceHint')}</Text>
            <Text style={styles.hint}>{tr('waDoNotAddNewNumber')}</Text>
          </>
        ) : null}
        {awaitingMeta && !connected ? (
          <Text style={styles.warn}>
            {status?.blocker_message?.trim() || tr('waAwaitingMetaApprovalBody')}
          </Text>
        ) : null}
        {status?.blocker_code && !awaitingMeta ? <Text style={styles.warn}>{status.blocker_code}</Text> : null}
        {conn?.rollout_blocked_reason ? <Text style={styles.warn}>{conn.rollout_blocked_reason}</Text> : null}
        {connected && conn?.connection_id && onEnableAi && onDisableAi ? (
          <ChannelCapabilityToggles
            toggles={{ dm: aiOn, comments: false }}
            busyKey={busy ? 'dm' : null}
            showComments={false}
            messagesLabel={tr('integrationToggleMessages')}
            commentsLabel={tr('toggleComments')}
            onToggle={(_key, value) => {
              if (value) onEnableAi(conn.connection_id);
              else onDisableAi(conn.connection_id);
            }}
          />
        ) : null}
      </IntegrationCardShell>
      {connected && conn?.connection_id ? (
        <WhatsAppCloudOpsPanel
          connectionId={conn.connection_id}
          busy={busy}
          onBusyChange={onBusyChange}
          onError={onError}
          onNotice={onNotice}
        />
      ) : null}
    </View>
  );
}

export function isWhatsAppApiError(err: unknown): err is ApiError {
  return err instanceof ApiError;
}

const styles = StyleSheet.create({
  wrap: { gap: 14 },
  hint: { color: colors.textMuted, fontSize: 12, lineHeight: 17, fontFamily: fonts.body },
  warn: { color: colors.danger, fontSize: 12, lineHeight: 17, fontFamily: fonts.body },
});
