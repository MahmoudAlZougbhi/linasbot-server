import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useState } from 'react';
import { Linking } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { onAuthCleared } from '../api/client';
import { tokenStore } from '../auth/tokenStore';
import { API_BASE } from '../config';
import { useSubscriptionGate } from '../features/billing/useSubscriptionGate';
import { BootSplash } from '../features/boot/BootSplash';
import type { CmProposalReview } from '../features/cm/cmProposalReview';
import { isCmProposalSection } from '../features/cm/cmProposalReview';
import type { ControlArea } from '../features/control/controlAreas';
import { tryRegisterOwnerPushScaffold } from '../features/notifications/pushScaffold';
import { useTheme } from '../theme';
import { AppScreenTree } from './AppScreenTree';
import { parseLiveChatDeepLink, RESOURCE_MAP, type Screen } from './navigation';

/**
 * Root navigation shell. Module screens stay mounted after first visit so
 * leave→reopen does not remount/refetch; auth epoch remounts on login/logout.
 */
export function AppShell() {
  const { resolved } = useTheme();
  const [screen, setScreen] = useState<Screen>({ name: 'boot' });
  const [bootDone, setBootDone] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [hasAccess, setHasAccess] = useState(false);
  const [isPlatformOwner, setIsPlatformOwner] = useState(false);
  const [resumeArea, setResumeArea] = useState<ControlArea | null>(null);
  const [authEpoch, setAuthEpoch] = useState(0);
  const subGate = useSubscriptionGate(hasAccess);
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
      const access = await tokenStore.getAccessToken();
      const user = await tokenStore.getUser();
      setIsPlatformOwner(user?.role === 'platform_owner');
      setHasAccess(Boolean(access));
      setAuthReady(true);
      if (access) {
        void tryRegisterOwnerPushScaffold();
      }
    })();
  }, []);

  useEffect(() => {
    return onAuthCleared(() => {
      setHasAccess(false);
      setIsPlatformOwner(false);
      bumpAuthEpoch();
    });
  }, [bumpAuthEpoch]);

  useEffect(() => {
    const applyUrl = (url: string | null) => {
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
  }, [hasAccess]);

  const finishBoot = useCallback(() => {
    setBootDone(true);
    if (!authReady) return;
    setScreen({ name: 'chat' });
  }, [authReady]);

  useEffect(() => {
    if (bootDone && authReady) {
      setScreen({ name: 'chat' });
    }
  }, [bootDone, authReady]);

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
      setScreen({ name: 'usage' });
      return;
    }
    if (area === 'livechat') {
      setScreen({ name: 'livechat', open: null });
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
    const target = RESOURCE_MAP[area];
    if (target) {
      setScreen({ name: 'resource', ...target });
      return;
    }
    setScreen({ name: 'chat' });
  }

  async function afterLogin() {
    const user = await tokenStore.getUser();
    setIsPlatformOwner(user?.role === 'platform_owner');
    setHasAccess(true);
    bumpAuthEpoch();
    void tryRegisterOwnerPushScaffold();
    const pending = resumeArea;
    setResumeArea(null);
    if (pending && pending !== 'integrations') {
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
    setIsPlatformOwner(false);
    setHasAccess(false);
    setResumeArea(null);
    bumpAuthEpoch();
    setScreen({ name: 'chat' });
  }

  function openArea(area: ControlArea) {
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
    if (!hasAccess) {
      setResumeArea(area);
      setScreen({ name: 'login' });
      return;
    }
    openAreaAuthed(area);
  }

  if (!bootDone || !authReady || screen.name === 'boot') {
    return (
      <SafeAreaProvider>
        <StatusBar style={resolved === 'dark' ? 'light' : 'dark'} />
        <BootSplash onDone={finishBoot} />
      </SafeAreaProvider>
    );
  }

  return (
    <SafeAreaProvider>
      <StatusBar style={resolved === 'dark' ? 'light' : 'dark'} />
      <AppScreenTree
        screen={screen}
        authEpoch={authEpoch}
        hasAccess={hasAccess}
        isPlatformOwner={isPlatformOwner}
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
    </SafeAreaProvider>
  );
}
