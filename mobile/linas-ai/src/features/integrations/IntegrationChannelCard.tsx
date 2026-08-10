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
  live_verified: boolean;
  effective_enabled: boolean;
  missing_scopes?: string[];
  blocker?: string | null;
  status?: string;
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
  onManageCommentPermissions: () => void;
  onConnect: () => void;
  onDisconnect: () => void;
};

export function defaultToggles(row: IntegrationRow): ChannelToggles {
  return row.toggles ?? { dm: false, comments: false };
}

export function commentsBlocker(row: IntegrationRow): string | null {
  return row.comments_blocker ?? row.comments_state?.blocker ?? null;
}

export function commentsStatusLabel(row: IntegrationRow, tr: (key: StringKey) => string): string | null {
  const state = row.comments_state;
  if (!state) return null;
  if (state.live_verified) return tr('commentsStatusLiveVerified');
  if (state.effective_enabled) return tr('commentsStatusReady');
  if (state.status === 'ready_to_enable') return tr('commentsStatusReadyToEnable');
  if (state.status === 'needs_webhook') return tr('commentsStatusNeedsWebhook');
  if (state.status === 'needs_permission' || commentsBlocker(row) === 'missing_comment_permissions') {
    return tr('commentsStatusNeedsPermission');
  }
  return null;
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
  onManageCommentPermissions,
  onConnect,
  onDisconnect,
}: Props) {
  const showToggles = !soon && (row.platform === 'instagram' || row.platform === 'facebook');
  const blocker = commentsBlocker(row);
  const statusLabel = commentsStatusLabel(row, tr);
  const needsCommentPerms = blocker === 'missing_comment_permissions';

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
              {blocker ? (
                <Text style={styles.blocker}>
                  {blocker === 'missing_comment_permissions'
                    ? tr('commentsBlockerMissingPermissions')
                    : blocker === 'connect_channel_first'
                      ? tr('commentsBlockerConnectFirst')
                      : blocker === 'missing_comment_webhook'
                        ? tr('commentsBlockerMissingWebhook')
                        : tr('commentsBlockerGeneric')}
                </Text>
              ) : null}
              {needsCommentPerms || (row.comments_state?.missing_scopes?.length ?? 0) > 0 ? (
                <PrimaryButton
                  label={
                    row.connected ? tr('manageCommentPermissions') : tr('reconnectWithCommentAccess')
                  }
                  onPress={onManageCommentPermissions}
                  loading={busy}
                  disabled={actionsDisabled}
                  variant="ghost"
                />
              ) : null}
            </>
          ) : null}
          {row.connected ? (
            <PrimaryButton
              label={tr('disconnect')}
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
