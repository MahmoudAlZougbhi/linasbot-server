import { Alert } from 'react-native';

import { ApiError } from '../../api/client';
import type { StringKey } from '../../i18n/locales/en';
import {
  IntegrationChannelCard,
  channelSubtitle,
  type IntegrationRow,
} from './IntegrationChannelCard';
import { disconnectTikTok, startTikTokOAuth } from './integrationsOAuth';
import type { IntegrationListRow } from './integrationsSchemas';

type Row = IntegrationListRow;

type Props = {
  row: Row;
  busy: boolean;
  busyToggleKey: 'dm' | 'comments' | null;
  actionsDisabled: boolean;
  tr: (key: StringKey) => string;
  onToggle: (key: 'dm' | 'comments', value: boolean) => void;
  onOpenMenu: () => void;
  onBusy: (platform: string | null) => void;
  onError: (message: string | null) => void;
  onAuthGate: () => void;
  title: string;
  soon: boolean;
};

export async function connectTikTokChannel(args: {
  onBusy: (platform: string | null) => void;
  onError: (message: string | null) => void;
  onAuthGate: () => void;
  actionError: string;
}): Promise<void> {
  args.onBusy('tiktok');
  args.onError(null);
  try {
    await startTikTokOAuth();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) args.onAuthGate();
    else args.onError(args.actionError);
  } finally {
    args.onBusy(null);
  }
}

export function confirmDisconnectTikTok(args: {
  accountName: string;
  tr: (key: StringKey) => string;
  onBusy: (platform: string | null) => void;
  onError: (message: string | null) => void;
  onAuthGate: () => void;
  onReload: () => Promise<unknown>;
}): void {
  Alert.alert(args.tr('disconnectAccount'), `${args.accountName}\n${args.tr('disconnectAccountConfirm')}`, [
    { text: args.tr('usersCancel'), style: 'cancel' },
    {
      text: args.tr('disconnect'),
      style: 'destructive',
      onPress: () => {
        void (async () => {
          args.onBusy('tiktok');
          args.onError(null);
          try {
            await disconnectTikTok();
            await args.onReload();
          } catch (err) {
            if (err instanceof ApiError && err.status === 401) args.onAuthGate();
            else args.onError(args.tr('integrationsActionError'));
          } finally {
            args.onBusy(null);
          }
        })();
      },
    },
  ]);
}

export function tiktokSheetTarget(row: Row, title: string) {
  return {
    kind: 'meta' as const,
    platform: 'tiktok' as const,
    title,
    subtitle: channelSubtitle(row as IntegrationRow),
  };
}

export function IntegrationsTikTokSection({
  row,
  busy,
  busyToggleKey,
  actionsDisabled,
  tr,
  onToggle,
  onOpenMenu,
  onBusy,
  onError,
  onAuthGate,
  title,
  soon,
}: Props) {
  return (
    <IntegrationChannelCard
      key="tiktok"
      row={row as IntegrationRow}
      title={title}
      soon={soon}
      busy={busy}
      busyToggleKey={busyToggleKey}
      actionsDisabled={actionsDisabled}
      tr={tr}
      onToggle={onToggle}
      onReconcileComments={() => undefined}
      onConnect={() =>
        void connectTikTokChannel({
          onBusy,
          onError,
          onAuthGate,
          actionError: tr('integrationsActionError'),
        })
      }
      onOpenMenu={onOpenMenu}
    />
  );
}
