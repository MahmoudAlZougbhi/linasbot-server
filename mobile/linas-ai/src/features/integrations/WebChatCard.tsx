import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing } from '../../theme';
import { IntegrationCardShell } from './IntegrationCardShell';
import { WebsiteIntegrationScreen } from './WebsiteIntegrationScreen';
import { fetchWebChatSettings, type WebChatSettings } from './webChatApi';
import {
  clearWebChatCardSnapshot,
  readWebChatCardSnapshot,
  writeWebChatCardSnapshot,
} from './webChatCardCache';
import {
  fetchWebChannelEntitledFromEntitlements,
  resolveWebPlanAllowed,
} from './webChatPlanAccess';

type Props = {
  onError?: (message: string) => void;
  onNotice?: (message: string) => void;
};

function statusKey(status: WebChatSettings['installation_status'] | undefined) {
  if (status === 'connected') return 'webChatStatusConnected';
  if (status === 'domain_mismatch') return 'webChatStatusDomainMismatch';
  if (status === 'disabled') return 'webChatStatusDisabled';
  return 'webChatStatusWaiting';
}

export function WebChatCard({ onError, onNotice }: Props) {
  const { tr } = useI18n();
  const cached = readWebChatCardSnapshot();
  const [settings, setSettings] = useState<WebChatSettings | null>(cached?.settings ?? null);
  const [entitlementWeb, setEntitlementWeb] = useState<boolean | null>(cached?.entitlementWeb ?? null);
  const [ready, setReady] = useState(cached !== null);
  const [detailOpen, setDetailOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const [data, entitled] = await Promise.all([
        fetchWebChatSettings(),
        fetchWebChannelEntitledFromEntitlements(),
      ]);
      writeWebChatCardSnapshot({ settings: data, entitlementWeb: entitled });
      setSettings(data);
      setEntitlementWeb(entitled);
      setReady(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      onError?.(tr('integrationsActionError'));
    }
  }, [onError, tr]);

  useEffect(() => {
    void load();
    return () => clearWebChatCardSnapshot();
  }, [load]);

  if (detailOpen) {
    return (
      <WebsiteIntegrationScreen
        onBack={() => {
          setDetailOpen(false);
          void load();
        }}
        onError={onError}
        onNotice={onNotice}
      />
    );
  }

  if (!ready) {
    return null;
  }

  const webPlanAllowed = resolveWebPlanAllowed(settings, entitlementWeb);
  const planBlocked = !webPlanAllowed;
  const connected = Boolean(settings?.connected);
  const statusLabel = tr(statusKey(settings?.installation_status));

  return (
    <View accessibilityRole="summary" style={styles.wrap}>
      <IntegrationCardShell
        platform="web"
        title={tr('platformWeb')}
        subtitle={connected ? settings?.site_url || tr('platformWeb') : tr('webChatSubtitle')}
        connected={connected}
        connectLabel={tr('webChatOpenSettings')}
        connectedLabel={tr('connected')}
        notConnectedLabel={tr('notConnected')}
        comingSoonLabel={tr('comingSoon')}
        healthLabel={statusLabel}
        menuLabel={tr('webChatOpenSettings')}
        showConnect={!planBlocked}
        showMenu={connected && !planBlocked}
        showHealth={connected}
        onConnect={() => setDetailOpen(true)}
        onMenu={() => setDetailOpen(true)}
      >
        {planBlocked ? <Text style={styles.warn}>{tr('webChatPlanRequired')}</Text> : null}
        {!planBlocked ? (
          <Pressable onPress={() => setDetailOpen(true)} style={styles.openBtn}>
            <Text style={styles.openText}>{tr('webChatOpenSettings')}</Text>
          </Pressable>
        ) : null}
      </IntegrationCardShell>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: spacing.md },
  warn: { fontFamily: fonts.body, fontSize: 13, color: colors.warning, marginBottom: spacing.sm },
  openBtn: { paddingVertical: 4 },
  openText: { fontFamily: fonts.bodyMedium, color: colors.accent, fontSize: 14 },
});
