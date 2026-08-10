import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useState } from 'react';
import { Linking } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { onAuthCleared } from './src/api/client';
import { API_BASE } from './src/config';
import { tokenStore } from './src/auth/tokenStore';
import { LoginScreen } from './src/features/auth/LoginScreen';
import { RegisterScreen } from './src/features/auth/RegisterScreen';
import { BillingScreen } from './src/features/billing/BillingScreen';
import { SubscriptionGateScreen } from './src/features/billing/SubscriptionGateScreen';
import { useSubscriptionGate } from './src/features/billing/useSubscriptionGate';
import { UsageScreen } from './src/features/billing/UsageScreen';
import { BootSplash } from './src/features/boot/BootSplash';
import { ChatScreen } from './src/features/chat/ChatScreen';
import { queueSetupHandoff } from './src/features/chat/pendingSetupHandoff';
import { FAQ_ASK_LINAS_PROMPT } from './src/features/faq/faqLanguages';
import { CmScreen } from './src/features/cm/CmScreen';
import { CmSectionScreen } from './src/features/cm/CmSectionScreen';
import type { CmProposalReview } from './src/features/cm/cmProposalReview';
import { isCmProposalSection } from './src/features/cm/cmProposalReview';
import type { ControlArea } from './src/features/control/controlAreas';
import { DashboardScreen } from './src/features/dashboard/DashboardScreen';
import { IntegrationsScreen } from './src/features/integrations/IntegrationsScreen';
import { LiveChatScreen } from './src/features/livechat/LiveChatScreen';
import { NotificationsScreen } from './src/features/notifications/NotificationsScreen';
import { tryRegisterOwnerPushScaffold } from './src/features/notifications/pushScaffold';
import { FaqScreen } from './src/features/faq/FaqScreen';
import { SettingsScreen } from './src/features/settings/SettingsScreen';
import { SimpleResourceScreen } from './src/features/shared/SimpleResourceScreen';
import { UsersScreen } from './src/features/users/UsersScreen';
import { LanguageProvider } from './src/i18n/LanguageContext';
import { ThemeProvider, useTheme } from './src/theme';

import { parseLiveChatDeepLink, RESOURCE_MAP, type Screen } from './src/app/navigation';

export default function App() {
  return (
    <ThemeProvider>
      <LanguageProvider>
        <AppBody />
      </LanguageProvider>
    </ThemeProvider>
  );
}

function AppBody() {
  const { resolved } = useTheme();
  const [screen, setScreen] = useState<Screen>({ name: 'boot' });
  const [bootDone, setBootDone] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [hasAccess, setHasAccess] = useState(false);
  const [isPlatformOwner, setIsPlatformOwner] = useState(false);
  const [resumeArea, setResumeArea] = useState<ControlArea | null>(null);
  const subGate = useSubscriptionGate(hasAccess);
  const showSubGate =
    hasAccess &&
    subGate.blocked &&
    screen.name !== 'billing' &&
    screen.name !== 'login' &&
    screen.name !== 'register';

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
    });
  }, []);

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
    if (!authReady) {
      return;
    }
    // App-first: always open main chat (guest or authenticated).
    setScreen({ name: 'chat' });
  }, [authReady]);

  useEffect(() => {
    if (bootDone && authReady) {
      setScreen({ name: 'chat' });
    }
  }, [bootDone, authReady]);

  async function afterLogin() {
    const user = await tokenStore.getUser();
    setIsPlatformOwner(user?.role === 'platform_owner');
    setHasAccess(true);
    void tryRegisterOwnerPushScaffold();
    await subGate.refresh();
    const pending = resumeArea;
    setResumeArea(null);
    if (pending && pending !== 'integrations') {
      openAreaAuthed(pending);
      return;
    }
    setScreen({ name: 'chat' });
  }

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
    setScreen({ name: 'chat' });
  }

  function openArea(area: ControlArea) {
    if (area === 'integrations') {
      // Guests land on Integrations → AuthGate (not a fake connect surface).
      setScreen({ name: 'integrations' });
      return;
    }
    if (area === 'users') {
      // Guests land on Users → AuthGate (same pattern as Integrations).
      setScreen({ name: 'users' });
      return;
    }
    if (area === 'notifications') {
      // Guests land on Notifications → AuthGate (no owner alerts for guests).
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
      {screen.name === 'login' ? (
        <LoginScreen
          onLoggedIn={() => void afterLogin()}
          onGoRegister={() => setScreen({ name: 'register' })}
          onBack={() => setScreen({ name: 'chat' })}
        />
      ) : null}
      {screen.name === 'register' ? (
        <RegisterScreen
          onBack={() => setScreen({ name: 'login' })}
          onDone={() => setScreen({ name: 'login' })}
        />
      ) : null}
      {showSubGate ? (
        <SubscriptionGateScreen
          loading={subGate.loading}
          onOpenSubscription={() => setScreen({ name: 'billing' })}
          onRefresh={() => void subGate.refresh()}
          onLogout={() => void logout()}
        />
      ) : null}
      {!showSubGate && screen.name === 'chat' ? (
        <ChatScreen
          isAuthenticated={hasAccess}
          isPlatformOwner={isPlatformOwner}
          onOpenArea={openArea}
          onOpenCmReview={openCmReview}
          onRequestLogin={() => setScreen({ name: 'login' })}
          onRequestRegister={() => setScreen({ name: 'register' })}
        />
      ) : null}
      {screen.name === 'settings' ? (
        <SettingsScreen
          onBack={() => setScreen({ name: 'chat' })}
          onLogout={() => void logout()}
          onOpenNotifications={() => setScreen({ name: 'notifications', backTo: 'settings' })}
          onOpenActions={() =>
            setScreen({ name: 'cm_section', section: 'actions', backTo: 'settings' })
          }
          onOpenAiLimits={() =>
            setScreen({ name: 'cm_section', section: 'ai_limits', backTo: 'settings' })
          }
        />
      ) : null}
      {screen.name === 'integrations' ? (
        <IntegrationsScreen
          onBack={() => setScreen({ name: 'chat' })}
          onRequestLogin={() => setScreen({ name: 'login' })}
          onRequestRegister={() => setScreen({ name: 'register' })}
        />
      ) : null}
      {screen.name === 'users' ? (
        <UsersScreen
          onBack={() => setScreen({ name: 'chat' })}
          onRequestLogin={() => {
            setResumeArea('users');
            setScreen({ name: 'login' });
          }}
          onRequestRegister={() => setScreen({ name: 'register' })}
        />
      ) : null}
      {screen.name === 'dashboard' ? (
        <DashboardScreen onBack={() => setScreen({ name: 'chat' })} isPlatformOwner={isPlatformOwner} />
      ) : null}
      {screen.name === 'billing' ? (
        <BillingScreen
          onBack={() => {
            void subGate.refresh().then(() => setScreen({ name: 'chat' }));
          }}
        />
      ) : null}
      {screen.name === 'usage' ? <UsageScreen onBack={() => setScreen({ name: 'chat' })} /> : null}
      {screen.name === 'livechat' ? (
        <LiveChatScreen onBack={() => setScreen({ name: 'chat' })} initialOpen={screen.open ?? null} />
      ) : null}
      {screen.name === 'notifications' ? (
        <NotificationsScreen
          isAuthenticated={hasAccess}
          onBack={() => {
            if (screen.backTo === 'settings') setScreen({ name: 'settings' });
            else setScreen({ name: 'chat' });
          }}
          onOpenLiveChat={(target) => setScreen({ name: 'livechat', open: target })}
          onRequestLogin={() => {
            setResumeArea('notifications');
            setScreen({ name: 'login' });
          }}
          onRequestRegister={() => setScreen({ name: 'register' })}
        />
      ) : null}
      {screen.name === 'cm' ? (
        <CmScreen
          onBack={() => setScreen({ name: 'chat' })}
          onOpenSection={(section) => setScreen({ name: 'cm_section', section, backTo: 'cm' })}
          onContinueSetup={(prompt) => {
            queueSetupHandoff({ text: prompt, mode: 'work', autoSend: true });
            setScreen({ name: 'chat' });
          }}
        />
      ) : null}
      {screen.name === 'cm_section' ? (
        <CmSectionScreen
          section={screen.section}
          proposalReview={screen.proposalReview ?? null}
          onBack={() => {
            if (screen.backTo === 'settings') {
              setScreen({ name: 'settings' });
              return;
            }
            if (screen.backTo === 'chat') {
              setScreen({ name: 'chat' });
              return;
            }
            setScreen({ name: 'cm' });
          }}
          backLabel={
            screen.backTo === 'settings'
              ? '← Back to Settings'
              : screen.backTo === 'chat'
                ? '← Back to chat'
                : '← Back to Content Management'
          }
        />
      ) : null}
      {screen.name === 'faq' ? (
        <FaqScreen
          onBack={() => setScreen({ name: 'chat' })}
          proposalReview={screen.proposalReview ?? null}
          onAskLinas={() => {
            queueSetupHandoff({ text: FAQ_ASK_LINAS_PROMPT, mode: 'work', autoSend: true });
            setScreen({ name: 'chat' });
          }}
        />
      ) : null}
      {screen.name === 'resource' ? (
        <SimpleResourceScreen
          title={screen.title}
          path={screen.path}
          onBack={() => setScreen({ name: 'chat' })}
        />
      ) : null}
    </SafeAreaProvider>
  );
}
