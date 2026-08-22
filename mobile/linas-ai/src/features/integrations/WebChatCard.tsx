import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing } from '../../theme';
import { ChannelCapabilityToggles } from './ChannelCapabilityToggles';
import { IntegrationCardShell } from './IntegrationCardShell';
import { WebsiteIntegrationScreen } from './WebsiteIntegrationScreen';
import { fetchWebChatSettings, saveWebChatSettings, type WebChatSettings } from './webChatApi';
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
  const [loadFailed, setLoadFailed] = useState(false);
  const [busyToggle, setBusyToggle] = useState(false);

  const load = useCallback(async () => {
    try {
      const [data, entitled] = await Promise.all([
        fetchWebChatSettings(),
        fetchWebChannelEntitledFromEntitlements(),
      ]);
      writeWebChatCardSnapshot({ settings: data, entitlementWeb: entitled });
      setSettings(data);
      setEntitlementWeb(entitled);
      setLoadFailed(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      // Keep the card visible; do not escalate to Integrations list load error.
      setLoadFailed(true);
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    void load();
    return () => clearWebChatCardSnapshot();
  }, [load]);

  async function onMessagesToggle(value: boolean) {
    setBusyToggle(true);
    try {
      const data = await saveWebChatSettings({ enabled: value });
      writeWebChatCardSnapshot({ settings: data, entitlementWeb });
      setSettings(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      onError?.(tr('integrationsToggleError'));
    } finally {
      setBusyToggle(false);
    }
  }

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

  // Parent screen already shows LinasLoadingIndicator until webChatReady.
  if (!ready) {
    return null;
  }

  // Unknown membership (failed fetch) must not hide Connect behind plan gating.
  const webPlanAllowed = loadFailed ? true : resolveWebPlanAllowed(settings, entitlementWeb);
  const planBlocked = !webPlanAllowed;
  const connected = Boolean(settings?.connected);
  const statusLabel = tr(statusKey(settings?.installation_status));
  const connectLabel = connected ? tr('webChatOpenSettings') : tr('connect');

  return (
    <View accessibilityRole="summary" style={styles.wrap}>
      <IntegrationCardShell
        platform="web"
        title={tr('platformWeb')}
        subtitle={connected ? settings?.site_url || tr('platformWeb') : tr('webChatSubtitle')}
        connected={connected}
        connectLabel={connectLabel}
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
        {loadFailed ? <Text style={styles.warn}>{tr('integrationsActionError')}</Text> : null}
        {!planBlocked && !loadFailed && settings && connected ? (
          <ChannelCapabilityToggles
            toggles={{ dm: Boolean(settings.enabled), comments: false }}
            busyKey={busyToggle ? 'dm' : null}
            showComments={false}
            messagesLabel={tr('integrationToggleMessages')}
            commentsLabel={tr('toggleComments')}
            onToggle={(_key, value) => void onMessagesToggle(value)}
          />
        ) : null}
        {!planBlocked && !loadFailed ? (
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
