import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useState } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { API_BASE } from './src/config';
import { tokenStore } from './src/auth/tokenStore';
import { LoginScreen } from './src/features/auth/LoginScreen';
import { RegisterScreen } from './src/features/auth/RegisterScreen';
import { BillingScreen } from './src/features/billing/BillingScreen';
import { UsageScreen } from './src/features/billing/UsageScreen';
import { BootSplash } from './src/features/boot/BootSplash';
import { ChatScreen } from './src/features/chat/ChatScreen';
import { CmScreen } from './src/features/cm/CmScreen';
import { CommentsScreen } from './src/features/control/CommentsScreen';
import type { ControlArea } from './src/features/control/controlAreas';
import { CreativeStudioScreen } from './src/features/creative/CreativeStudioScreen';
import { DashboardScreen } from './src/features/dashboard/DashboardScreen';
import { IntegrationsScreen } from './src/features/integrations/IntegrationsScreen';
import { LiveChatScreen } from './src/features/livechat/LiveChatScreen';
import { SettingsScreen } from './src/features/settings/SettingsScreen';
import { SimpleResourceScreen } from './src/features/shared/SimpleResourceScreen';
import { LanguageProvider } from './src/i18n/LanguageContext';

type Screen =
  | { name: 'boot' }
  | { name: 'login' }
  | { name: 'register' }
  | { name: 'chat' }
  | { name: 'settings' }
  | { name: 'integrations' }
  | { name: 'creative' }
  | { name: 'dashboard' }
  | { name: 'billing' }
  | { name: 'usage' }
  | { name: 'livechat' }
  | { name: 'cm' }
  | { name: 'comments' }
  | { name: 'resource'; title: string; path: string };

const RESOURCE_MAP: Partial<Record<ControlArea, { title: string; path: string }>> = {
  users: { title: 'Users', path: '/api/auth/users' },
  scheduled: { title: 'Scheduled', path: '/api/schedule/posts' },
  owner: { title: 'Owner Control Center', path: '/api/platform/metrics' },
};

export default function App() {
  const [screen, setScreen] = useState<Screen>({ name: 'boot' });
  const [bootDone, setBootDone] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [hasAccess, setHasAccess] = useState(false);
  const [isPlatformOwner, setIsPlatformOwner] = useState(false);

  useEffect(() => {
    void (async () => {
      const access = await tokenStore.getAccessToken();
      const user = await tokenStore.getUser();
      setIsPlatformOwner(user?.role === 'platform_owner');
      setHasAccess(Boolean(access));
      setAuthReady(true);
    })();
  }, []);

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
    setScreen({ name: 'chat' });
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
    setScreen({ name: 'chat' });
  }

  function openArea(area: ControlArea) {
    if (!hasAccess) {
      setScreen({ name: 'login' });
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
    if (area === 'create') {
      setScreen({ name: 'creative' });
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
      setScreen({ name: 'livechat' });
      return;
    }
    if (area === 'cm') {
      setScreen({ name: 'cm' });
      return;
    }
    if (area === 'comments') {
      setScreen({ name: 'comments' });
      return;
    }
    const target = RESOURCE_MAP[area];
    if (target) {
      setScreen({ name: 'resource', ...target });
    }
  }

  if (!bootDone || !authReady || screen.name === 'boot') {
    return (
      <LanguageProvider>
        <SafeAreaProvider>
          <StatusBar style="dark" />
          <BootSplash onDone={finishBoot} />
        </SafeAreaProvider>
      </LanguageProvider>
    );
  }

  return (
    <LanguageProvider>
      <SafeAreaProvider>
        <StatusBar style="dark" />
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
        {screen.name === 'chat' ? (
          <ChatScreen
            isAuthenticated={hasAccess}
            isPlatformOwner={isPlatformOwner}
            onOpenArea={openArea}
            onLogout={() => void logout()}
            onRequestLogin={() => setScreen({ name: 'login' })}
            onRequestRegister={() => setScreen({ name: 'register' })}
          />
        ) : null}
        {screen.name === 'settings' ? (
          <SettingsScreen onBack={() => setScreen({ name: 'chat' })} onLogout={() => void logout()} />
        ) : null}
        {screen.name === 'integrations' ? (
          <IntegrationsScreen onBack={() => setScreen({ name: 'chat' })} />
        ) : null}
        {screen.name === 'creative' ? (
          <CreativeStudioScreen onBack={() => setScreen({ name: 'chat' })} />
        ) : null}
        {screen.name === 'dashboard' ? (
          <DashboardScreen onBack={() => setScreen({ name: 'chat' })} isPlatformOwner={isPlatformOwner} />
        ) : null}
        {screen.name === 'billing' ? <BillingScreen onBack={() => setScreen({ name: 'chat' })} /> : null}
        {screen.name === 'usage' ? <UsageScreen onBack={() => setScreen({ name: 'chat' })} /> : null}
        {screen.name === 'livechat' ? <LiveChatScreen onBack={() => setScreen({ name: 'chat' })} /> : null}
        {screen.name === 'cm' ? <CmScreen onBack={() => setScreen({ name: 'chat' })} /> : null}
        {screen.name === 'comments' ? <CommentsScreen onBack={() => setScreen({ name: 'chat' })} /> : null}
        {screen.name === 'resource' ? (
          <SimpleResourceScreen
            title={screen.title}
            path={screen.path}
            onBack={() => setScreen({ name: 'chat' })}
          />
        ) : null}
      </SafeAreaProvider>
    </LanguageProvider>
  );
}
