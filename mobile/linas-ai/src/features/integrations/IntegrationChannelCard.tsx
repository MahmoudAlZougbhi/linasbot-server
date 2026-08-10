import { StyleSheet, Text, View } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { StatusChip } from '../../components/StatusChip';
import type { StringKey } from '../../i18n/locales/en';
import { colors, fonts, radii, spacing } from '../../theme';
import {
  ChannelCapabilityToggles,
  type ChannelToggles,
} from './ChannelCapabilityToggles';

export type CommentsState = {
  requested_enabled: boolean;
  permission_present: boolean;
  webhook_subscribed: boolean;
  tenant_action_enabled?: boolean;
  connection_healthy?: boolean;
  live_verified: boolean;
  effective_enabled: boolean;
  missing_scopes?: string[];
  blocker?: string | null;
  blocker_code?: string | null;
  blocker_message?: string | null;
  status?: string;
  last_checked_at?: number;
};

export type IntegrationRow = {
  platform: string;
  label: string;
  connected: boolean;
  coming_soon?: boolean;
  connectable?: boolean;
  binding_ids?: string[];
  toggles?: ChannelToggles;
  comments_blocker?: string;
  comments_state?: CommentsState;
  dm_state?: CommentsState;
};

type Props = {
  row: IntegrationRow;
  title: string;
  soon: boolean;
  busy: boolean;
  busyToggleKey: 'dm' | 'comments' | null;
  actionsDisabled: boolean;
  tr: (key: StringKey) => string;
  onToggle: (key: 'dm' | 'comments', value: boolean) => void;
  onManageMetaAccess: () => void;
  onReconcileComments: () => void;
  onConnect: () => void;
  onDisconnect: () => void;
};

export function defaultToggles(row: IntegrationRow): ChannelToggles {
  return row.toggles ?? { dm: false, comments: false };
}

export function commentsBlocker(row: IntegrationRow): string | null {
  return (
    row.comments_blocker ??
    row.comments_state?.blocker_code ??
    row.comments_state?.blocker ??
    null
  );
}

const STATUS_I18N: Record<string, StringKey> = {
  disabled: 'commentsStatusDisabled',
  permission_required: 'commentsStatusPermissionRequired',
  meta_approval_required: 'commentsStatusMetaApprovalRequired',
  webhook_setup_required: 'commentsStatusWebhookSetupRequired',
  reauthorization_required: 'commentsStatusReauthorizationRequired',
  configuring: 'commentsStatusConfiguring',
  ready: 'commentsStatusReady',
  enabled: 'commentsStatusEnabled',
  live_verified: 'commentsStatusLiveVerified',
  error: 'commentsStatusError',
  // Back-compat from PR #159
  ready_to_enable: 'commentsStatusReady',
  needs_webhook: 'commentsStatusWebhookSetupRequired',
  needs_permission: 'commentsStatusPermissionRequired',
  off: 'commentsStatusDisabled',
};

export function commentsStatusLabel(row: IntegrationRow, tr: (key: StringKey) => string): string | null {
  const state = row.comments_state;
  if (!state) return null;
  if (state.live_verified) return tr('commentsStatusLiveVerified');
  if (state.effective_enabled) return tr('commentsStatusEnabled');
  const key = STATUS_I18N[state.status || ''];
  return key ? tr(key) : null;
}

function blockerCopy(blocker: string, tr: (key: StringKey) => string): string {
  switch (blocker) {
    case 'missing_comment_permissions':
      return tr('commentsBlockerMissingPermissions');
    case 'connect_channel_first':
      return tr('commentsBlockerConnectFirst');
    case 'missing_comment_webhook':
      return tr('commentsBlockerMissingWebhook');
    case 'meta_approval_required':
      return tr('commentsBlockerMetaApproval');
    case 'reauthorization_required':
    case 'connection_unhealthy':
      return tr('commentsBlockerReauthorization');
    default:
      return tr('commentsBlockerGeneric');
  }
}

export function IntegrationChannelCard({
  row,
  title,
  soon,
  busy,
  busyToggleKey,
  actionsDisabled,
  tr,
  onToggle,
  onManageMetaAccess,
  onReconcileComments,
  onConnect,
  onDisconnect,
}: Props) {
  const showToggles = !soon && (row.platform === 'instagram' || row.platform === 'facebook');
  const blocker = commentsBlocker(row);
  const statusLabel = commentsStatusLabel(row, tr);
  const needsMetaAccess =
    blocker === 'missing_comment_permissions' ||
    blocker === 'meta_approval_required' ||
    blocker === 'reauthorization_required' ||
    blocker === 'connection_unhealthy' ||
    (row.comments_state?.missing_scopes?.length ?? 0) > 0;
  const needsWebhook = blocker === 'missing_comment_webhook';

  return (
    <View style={styles.card}>
      <View style={styles.head}>
        <Text style={styles.cardTitle}>{title}</Text>
        {soon ? (
          <StatusChip label={tr('comingSoon')} tone="soon" />
        ) : (
          <StatusChip
            label={row.connected ? tr('connected') : tr('notConnected')}
            tone={row.connected ? 'ok' : 'neutral'}
          />
        )}
      </View>
      {soon ? (
        <Text style={styles.soonHint}>{tr('comingSoon')}</Text>
      ) : (
        <>
          {showToggles ? (
            <>
              <ChannelCapabilityToggles
                toggles={defaultToggles(row)}
                busyKey={busyToggleKey}
                disabled={actionsDisabled}
                onToggle={onToggle}
              />
              {statusLabel ? <Text style={styles.statusHint}>{statusLabel}</Text> : null}
              {blocker ? <Text style={styles.blocker}>{blockerCopy(blocker, tr)}</Text> : null}
              {needsMetaAccess ? (
                <PrimaryButton
                  label={
                    row.connected ? tr('manageMetaAccess') : tr('reconnectWithCommentAccess')
                  }
                  onPress={onManageMetaAccess}
                  loading={busy}
                  disabled={actionsDisabled}
                  variant="ghost"
                />
              ) : null}
              {needsWebhook ? (
                <PrimaryButton
                  label={tr('reconcileCommentWebhooks')}
                  onPress={onReconcileComments}
                  loading={busy}
                  disabled={actionsDisabled}
                  variant="ghost"
                />
              ) : null}
            </>
          ) : null}
          {row.connected ? (
            <PrimaryButton
              label={tr('disconnectAccount')}
              onPress={onDisconnect}
              loading={busy}
              disabled={actionsDisabled}
              variant="danger"
            />
          ) : (
            <PrimaryButton
              label={tr('connect')}
              onPress={onConnect}
              loading={busy}
              disabled={actionsDisabled}
            />
          )}
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    padding: spacing.lg,
    borderColor: colors.border,
    borderWidth: 1,
    gap: spacing.md,
  },
  head: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  cardTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 17 },
  soonHint: { color: colors.textDim, fontFamily: fonts.body, fontSize: 13 },
  statusHint: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12 },
  blocker: { color: colors.danger, fontFamily: fonts.body, fontSize: 13 },
});
