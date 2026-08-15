import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing } from '../../theme';
import { IntegrationCardShell } from './IntegrationCardShell';
import { WebsiteIntegrationScreen } from './WebsiteIntegrationScreen';
import { fetchWebChatSettings, type WebChatSettings } from './webChatApi';
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
  const [settings, setSettings] = useState<WebChatSettings | null>(null);
  const [entitlementWeb, setEntitlementWeb] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailOpen, setDetailOpen] = useState(false);

  const webPlanAllowed = resolveWebPlanAllowed(settings, entitlementWeb);
  const planBlocked = !webPlanAllowed;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [data, entitled] = await Promise.all([
        fetchWebChatSettings(),
        fetchWebChannelEntitledFromEntitlements(),
      ]);
      setSettings(data);
      setEntitlementWeb(entitled);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      onError?.(tr('integrationsActionError'));
    } finally {
      setLoading(false);
    }
  }, [onError, tr]);

  useEffect(() => {
    void load();
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

  const connected = Boolean(settings?.connected);
  const statusLabel = tr(statusKey(settings?.installation_status));

  return (
    <View accessibilityRole="summary" style={styles.wrap}>
      <IntegrationCardShell
        platform="web"
        title={tr('platformWeb')}
        subtitle={connected ? settings?.site_url || tr('platformWeb') : tr('webChatSubtitle')}
        connected={connected}
        busy={loading}
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
