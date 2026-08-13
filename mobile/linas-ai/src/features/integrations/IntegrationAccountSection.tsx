import { Image, StyleSheet, Text, View } from 'react-native';

import type { StringKey } from '../../i18n/locales/en';
import { colors, fonts, radii, spacing } from '../../theme';

export type IntegrationAccountDisplay = {
  display_name: string;
  username?: string | null;
  profile_image_url?: string | null;
  connection_status?: 'connected' | 'needs_reconnect' | 'error' | 'disconnected';
  last_synced_at?: number | null;
};

type Props = {
  platform: 'instagram' | 'facebook';
  accounts: IntegrationAccountDisplay[];
  connectionStatus: 'connected' | 'needs_reconnect' | 'error' | 'disconnected';
  lastSyncedAt?: number | null;
  tr: (key: StringKey) => string;
};

function statusTone(status: Props['connectionStatus']): 'ok' | 'warn' | 'neutral' {
  if (status === 'connected') return 'ok';
  if (status === 'needs_reconnect' || status === 'error') return 'warn';
  return 'neutral';
}

function statusLabel(status: Props['connectionStatus'], tr: Props['tr']): string {
  switch (status) {
    case 'connected':
      return tr('integrationStatusConnected');
    case 'needs_reconnect':
      return tr('integrationStatusNeedsReconnect');
    case 'error':
      return tr('integrationStatusError');
    default:
      return tr('notConnected');
  }
}

function avatarLetter(name: string): string {
  const trimmed = name.replace(/^@/, '').trim();
  return (trimmed[0] || '?').toUpperCase();
}

function formatLastSynced(ts: number | null | undefined, tr: Props['tr']): string | null {
  if (!ts || ts <= 0) return null;
  const date = new Date(ts * 1000);
  if (Number.isNaN(date.getTime())) return null;
  return `${tr('integrationLastSynced')}: ${date.toLocaleString()}`;
}

export function IntegrationAccountSection({
  platform,
  accounts,
  connectionStatus,
  lastSyncedAt,
  tr,
}: Props) {
  if (!accounts.length) return null;

  const tone = statusTone(connectionStatus);
  const synced = formatLastSynced(lastSyncedAt, tr);

  return (
    <View style={styles.wrap}>
      {accounts.map((account, index) => (
        <View key={`${account.display_name}-${index}`} style={styles.accountRow}>
          {account.profile_image_url ? (
            <Image source={{ uri: account.profile_image_url }} style={styles.avatar} />
          ) : (
            <View style={styles.avatarPlaceholder}>
              <Text style={styles.avatarLetter}>{avatarLetter(account.display_name)}</Text>
            </View>
          )}
          <View style={styles.meta}>
            <Text style={styles.name}>{account.display_name}</Text>
            {platform === 'facebook' && account.username ? (
              <Text style={styles.sub}>{account.username}</Text>
            ) : null}
            {platform === 'instagram' &&
            account.username &&
            !account.display_name.includes('@') ? (
              <Text style={styles.sub}>@{account.username}</Text>
            ) : null}
          </View>
        </View>
      ))}
      <View style={styles.statusRow}>
        <View style={[styles.statusDot, tone === 'ok' ? styles.dotOk : styles.dotWarn]} />
        <Text style={[styles.statusText, tone === 'warn' ? styles.statusWarn : null]}>
          {statusLabel(connectionStatus, tr)}
        </Text>
      </View>
      {synced ? <Text style={styles.synced}>{synced}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: spacing.sm,
    paddingBottom: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  accountRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: radii.pill,
    backgroundColor: colors.surfaceAlt,
  },
  avatarPlaceholder: {
    width: 44,
    height: 44,
    borderRadius: radii.pill,
    backgroundColor: colors.surfaceAlt,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarLetter: {
    color: colors.textMuted,
    fontFamily: fonts.bodyMedium,
    fontSize: 18,
  },
  meta: { flex: 1, gap: 2 },
  name: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 16 },
  sub: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  dotOk: { backgroundColor: colors.mint },
  dotWarn: { backgroundColor: colors.warning },
  statusText: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12 },
  statusWarn: { color: colors.warning },
  synced: { color: colors.textDim, fontFamily: fonts.body, fontSize: 11 },
});
