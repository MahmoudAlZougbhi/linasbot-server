import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useState } from 'react';
import { Linking, StyleSheet, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { onAuthCleared } from '../api/client';
import { rotateGuestSessionId, rotateGuestSessionOnAppLaunch } from '../auth/guestSession';
import { bootPersistedAuth } from '../auth/restoreOwnerSession';
import { tokenStore } from '../auth/tokenStore';
import { scheduleIdlePrefetch } from '../cache/idlePrefetch';
import '../cache/bindSessionCaches';
import { API_BASE } from '../config';
import { AppUpdateBanner } from '../features/appVersion/AppUpdateBanner';
import { AppUpdateGateScreen } from '../features/appVersion/AppUpdateGateScreen';
import { useAppVersionCheck } from '../features/appVersion/useAppVersionCheck';
import { useSubscriptionGate } from '../features/billing/useSubscriptionGate';
import { BootSplash } from '../features/boot/BootSplash';
import type { CmProposalReview } from '../features/cm/cmProposalReview';
import { isCmProposalSection } from '../features/cm/cmProposalReview';
import type { ControlArea } from '../features/control/controlAreas';
import { tryRegisterOwnerPushScaffold } from '../features/notifications/pushScaffold';
import { ModuleNavProvider } from '../features/nav/ModuleNavContext';
import { useTheme } from '../theme';
import { AppScreenTree } from './AppScreenTree';
import { buildModuleNavValue, makeChatNavActions, useAreaFocusNonce } from './moduleNav';
import { parseIntegrationsDeepLink, parseLiveChatDeepLink, type Screen } from './navigation';

/**
 * Root navigation shell. Chat, Live Chat, Dashboard, and CM stay mounted after
 * first visit (hidden). Other tools unmount and paint from the query cache.
 * Auth epoch remounts keep-mounted panes on login/logout.
 */
export function AppShell() {
  const { resolved } = useTheme();
  const [screen, setScreen] = useState<Screen>({ name: 'boot' });
  const [bootDone, setBootDone] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [hasAccess, setHasAccess] = useState(false);
  const [resumeArea, setResumeArea] = useState<ControlArea | null>(null);
  const [authEpoch, setAuthEpoch] = useState(0);
  const [updateBannerDismissed, setUpdateBannerDismissed] = useState(false);
  const [areaFocusNonce, bumpAreaFocus] = useAreaFocusNonce();
  const subGate = useSubscriptionGate(hasAccess);
  const versionCheck = useAppVersionCheck(bootDone && authReady);
  const showSubGate =
    hasAccess &&
    subGate.blocked &&
    screen.name !== 'billing' &&
    screen.name !== 'login' &&
    screen.name !== 'register';

  const bumpAuthEpoch = useCallback(() => {
    setAuthEpoch((n) => n + 1);
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const has = await bootPersistedAuth(tokenStore, rotateGuestSessionOnAppLaunch);
        setHasAccess(has);
        if (has) {
          void tryRegisterOwnerPushScaffold();
        }
      } finally {
        setAuthReady(true);
      }
    })();
  }, []);

  useEffect(() => {
    if (!bootDone || !hasAccess) return;
    const ac = new AbortController();
    const cancelIdle = scheduleIdlePrefetch(ac.signal);
    return () => {
      ac.abort();
      cancelIdle();
    };
  }, [bootDone, hasAccess, authEpoch]);

  useEffect(() => {
    return onAuthCleared(() => {
      void rotateGuestSessionId().then(() => {
        setHasAccess(false);
        bumpAuthEpoch();
      });
    });
  }, [bumpAuthEpoch]);

  useEffect(() => {
    const applyUrl = (url: string | null) => {
      const integrations = parseIntegrationsDeepLink(url);
      if (integrations) {
        bumpAreaFocus();
        setScreen({ name: 'integrations' });
        return;
      }
      const target = parseLiveChatDeepLink(url);
      if (!target) return;
      if (!hasAccess) {
        setResumeArea('livechat');
        setScreen({ name: 'login' });
        return;
      }
      setScreen({ name: 'livechat', open: target });
    };
    void Linking.getInitialURL().then(applyUrl);
    const sub = Linking.addEventListener('url', (event) => applyUrl(event.url));
    return () => sub.remove();
  }, [hasAccess, bumpAreaFocus]);

  const finishBoot = useCallback(() => {
    setBootDone(true);
    setScreen((current) => (current.name === 'boot' ? { name: 'chat' } : current));
  }, []);

  useEffect(() => {
    if (bootDone || authReady) {
      setScreen((current) => (current.name === 'boot' ? { name: 'chat' } : current));
    }
  }, [authReady, bootDone]);

  function openAreaAuthed(area: ControlArea) {
    if (subGate.blocked && area !== 'subscription') {
      setScreen({ name: 'chat' });
      return;
    }
    if (area === 'settings') {
      setScreen({ name: 'settings' });
      return;
    }
    if (area === 'integrations') {
      setScreen({ name: 'integrations' });
      return;
    }
    if (area === 'users') {
      setScreen({ name: 'users' });
      return;
    }
    if (area === 'dashboard') {
      setScreen({ name: 'dashboard' });
      return;
    }
    if (area === 'subscription') {
      setScreen({ name: 'billing' });
      return;
    }
    if (area === 'usage') {
      setScreen({ name: 'dashboard' });
      return;
    }
    if (area === 'livechat') {
      setScreen({ name: 'livechat', open: null });
      return;
    }
    if (area === 'requests') {
      setScreen({ name: 'requests' });
      return;
    }
    if (area === 'notifications') {
      setScreen({ name: 'notifications', backTo: 'chat' });
      return;
    }
    if (area === 'cm') {
      setScreen({ name: 'cm' });
      return;
    }
    if (area === 'faq') {
      setScreen({ name: 'faq' });
      return;
    }
    if (area === 'smartFollowUp') {
      setScreen({ name: 'smartFollowUp' });
      return;
    }
    if (area === 'owner') {
      setScreen({ name: 'owner' });
      return;
    }
    setScreen({ name: 'chat' });
  }

  async function afterLogin() {
    setHasAccess(true);
    bumpAuthEpoch();
    void tryRegisterOwnerPushScaffold();
    const pending = resumeArea;
    setResumeArea(null);
    if (pending === 'integrations') {
      bumpAreaFocus();
      setScreen({ name: 'integrations' });
      return;
    }
    if (pending) {
      openAreaAuthed(pending);
      return;
    }
    setScreen({ name: 'chat' });
  }

  function openCmReview(review: CmProposalReview) {
    if (!hasAccess) {
      setResumeArea(review.section === 'faq' ? 'faq' : 'cm');
      setScreen({ name: 'login' });
      return;
    }
    if (review.section === 'faq') {
      setScreen({ name: 'faq', proposalReview: review });
      return;
    }
    if (review.section === 'prices' || review.section === 'services') {
      setScreen({ name: 'services', backTo: 'chat', proposalReview: review });
      return;
    }
    if (isCmProposalSection(review.section)) {
      setScreen({
        name: 'cm_section',
        section: review.section,
        backTo: 'chat',
        proposalReview: review,
      });
      return;
    }
    setScreen({ name: 'cm' });
  }

  async function logout() {
    try {
      const access = await tokenStore.getAccessToken();
      if (access) {
        await fetch(`${API_BASE}/api/auth/mobile/logout`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${access}`, Accept: 'application/json' },
        });
      }
    } catch {
      // Local clear still proceeds.
    }
    await tokenStore.clear();
    await rotateGuestSessionId();
    setHasAccess(false);
    setResumeArea(null);
    bumpAuthEpoch();
    setScreen({ name: 'chat' });
  }

  function openArea(area: ControlArea) {
    // Guests cannot open workspace tools (CM, Integrations, Live Chat, etc.).
    if (!hasAccess) {
      setResumeArea(area);
      setScreen({ name: 'login' });
      return;
    }
    if (area === 'integrations') {
      setScreen({ name: 'integrations' });
      return;
    }
    if (area === 'users') {
      setScreen({ name: 'users' });
      return;
    }
    if (area === 'notifications') {
      setScreen({ name: 'notifications', backTo: 'chat' });
      return;
    }
    openAreaAuthed(area);
  }

  const goChat = useCallback(() => {
    if (screen.name === 'billing') {
      void subGate.refresh();
    }
    setScreen({ name: 'chat' });
  }, [screen.name, subGate]);

  const { startNewChat, openChat } = makeChatNavActions(goChat);
  const moduleNav = buildModuleNavValue({
    hasAccess,
    openArea,
    goChat,
    startNewChat,
    openChat,
    setScreen,
    areaFocusNonce,
    screen,
  });

  const showApp = bootDone || authReady;
  const treeScreen = screen.name === 'boot' ? { name: 'chat' as const } : screen;

  if (bootDone && versionCheck.forceUpdate && versionCheck.result) {
    return (
      <SafeAreaProvider>
        <StatusBar style={resolved === 'dark' ? 'light' : 'dark'} />
        <AppUpdateGateScreen check={versionCheck.result} />
      </SafeAreaProvider>
    );
  }

  const showUpdateBanner =
    bootDone &&
    versionCheck.updateAvailable &&
    versionCheck.result !== null &&
    !updateBannerDismissed;

  return (
    <SafeAreaProvider>
      <StatusBar style={!bootDone ? 'light' : resolved === 'dark' ? 'light' : 'dark'} />
      {showUpdateBanner ? (
        <AppUpdateBanner
          check={versionCheck.result!}
          onDismiss={() => setUpdateBannerDismissed(true)}
        />
      ) : null}
      {showApp ? (
        <View
          style={styles.tree}
          accessibilityElementsHidden={!bootDone}
          importantForAccessibility={bootDone ? 'auto' : 'no-hide-descendants'}
        >
          <ModuleNavProvider value={moduleNav}>
            <AppScreenTree
              screen={treeScreen}
              authEpoch={authEpoch}
              hasAccess={hasAccess}
              showSubGate={showSubGate}
              subGateLoading={subGate.loading}
              onOpenArea={openArea}
              onOpenCmReview={openCmReview}
              setScreen={setScreen}
              setResumeArea={setResumeArea}
              afterLogin={() => void afterLogin()}
              logout={() => void logout()}
              refreshSubGate={() => subGate.refresh()}
            />
          </ModuleNavProvider>
        </View>
      ) : (
        <View style={styles.tree} />
      )}
      {!bootDone ? (
        <View style={styles.splashOverlay} pointerEvents="auto">
          <BootSplash appReady={authReady} onDone={finishBoot} />
        </View>
      ) : null}
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  tree: { flex: 1 },
  splashOverlay: {
    ...StyleSheet.absoluteFill,
    zIndex: 20,
  },
});
