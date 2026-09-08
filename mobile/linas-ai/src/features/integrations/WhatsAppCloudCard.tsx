import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts } from '../../theme';
import { ChannelCapabilityToggles, type ChannelToggleKey } from './ChannelCapabilityToggles';
import { IntegrationCardShell } from './IntegrationCardShell';
import { WhatsAppCoexistenceConfirm } from './WhatsAppCoexistenceConfirm';
import {
  isWhatsAppAppReviewTest,
  whatsappConnectionSubtitle,
} from './whatsappCloudPresentation';
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
  busyKey?: ChannelToggleKey | null;
  onConnect: () => void;
  onOpenMenu?: () => void;
  onEnableAi?: (connectionId: string) => void;
  onDisableAi?: (connectionId: string) => void;
  onEnableCalls?: (connectionId: string) => void;
  onDisableCalls?: (connectionId: string) => void;
};

export function whatsappCardSubtitle(status: WhatsAppCloudStatus | null, fallback: string): string {
  const conn = status?.connection;
  return status?.lifecycle_status === 'connected'
    ? whatsappConnectionSubtitle(conn, fallback)
    : fallback;
}

export function WhatsAppCloudCard({
  status,
  busy,
  busyKey = null,
  onConnect,
  onOpenMenu,
  onEnableAi,
  onDisableAi,
  onEnableCalls,
  onDisableCalls,
}: Props) {
  const { tr } = useI18n();
  const [confirmOpen, setConfirmOpen] = useState(false);

  const lifecycle = status?.lifecycle_status || 'disconnected';
  const connected = lifecycle === 'connected';
  const connectable = status?.connectable === true;
  const awaitingMeta =
    status?.awaiting_meta_approval === true ||
    (!connectable && !connected && !status?.pilot_entitled && status?.public_availability !== true);
  const conn = status?.connection;
  const appReviewTest = isWhatsAppAppReviewTest(conn);
  const subtitle = whatsappCardSubtitle(status, tr('integrationWhatsAppHandle'));
  const healthy = connected;
  const aiOn = Boolean(conn?.ai_default_enabled);
  const callsOn = Boolean(conn?.calls_enabled);
  const showToggles = Boolean(connected && conn?.connection_id && onEnableAi && onDisableAi);

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
        onConnect={() => {
          if (busy) return;
          setConfirmOpen(true);
        }}
        onMenu={onOpenMenu}
      >
        {!connected && connectable && confirmOpen ? (
          <WhatsAppCoexistenceConfirm
            busy={busy}
            onConfirm={() => {
              setConfirmOpen(false);
              onConnect();
            }}
            onCancel={() => setConfirmOpen(false)}
          />
        ) : null}
        {!connected && connectable && !confirmOpen ? (
          <>
            <Text style={styles.hint}>{tr('waCoexistenceHint')}</Text>
            <Text style={styles.hint}>{tr('waDoNotAddNewNumber')}</Text>
          </>
        ) : null}
        {connected && conn?.coexistence_mode && !appReviewTest ? (
          <Text style={styles.hint}>{tr('waCoexistenceOn')}</Text>
        ) : null}
        {awaitingMeta && !connected ? (
          <Text style={styles.warn}>
            {status?.blocker_message?.trim() || tr('waAwaitingMetaApprovalBody')}
          </Text>
        ) : null}
        {status?.blocker_code && !awaitingMeta ? <Text style={styles.warn}>{status.blocker_code}</Text> : null}
        {conn?.rollout_blocked_reason ? <Text style={styles.warn}>{conn.rollout_blocked_reason}</Text> : null}
        {showToggles && conn?.connection_id ? (
          <ChannelCapabilityToggles
            toggles={{ dm: aiOn, comments: false, calls: callsOn }}
            busyKey={busy ? busyKey || 'dm' : null}
            showComments={false}
            showCalls={Boolean(onEnableCalls && onDisableCalls)}
            messagesLabel={tr('integrationToggleMessages')}
            commentsLabel={tr('toggleComments')}
            callsLabel={tr('integrationToggleWhatsAppCall')}
            onToggle={(key, value) => {
              if (key === 'calls') {
                if (value) onEnableCalls?.(conn.connection_id);
                else onDisableCalls?.(conn.connection_id);
                return;
              }
              if (value) onEnableAi?.(conn.connection_id);
              else onDisableAi?.(conn.connection_id);
            }}
          />
        ) : null}
      </IntegrationCardShell>
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
