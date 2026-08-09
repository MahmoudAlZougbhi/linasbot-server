import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { tokenStore } from './src/auth/tokenStore';
import { LoginScreen } from './src/features/auth/LoginScreen';
import { RegisterScreen } from './src/features/auth/RegisterScreen';
import { ChatScreen } from './src/features/chat/ChatScreen';
import { ControlCenterScreen, type ControlArea } from './src/features/control/ControlCenterScreen';
import { CreativeStudioScreen } from './src/features/creative/CreativeStudioScreen';
import { IntegrationsScreen } from './src/features/integrations/IntegrationsScreen';
import { SettingsScreen } from './src/features/settings/SettingsScreen';
import { SimpleResourceScreen } from './src/features/shared/SimpleResourceScreen';
import { colors } from './src/theme/colors';

type Screen =
  | { name: 'boot' }
  | { name: 'login' }
  | { name: 'register' }
  | { name: 'chat' }
  | { name: 'control' }
  | { name: 'settings' }
  | { name: 'integrations' }
  | { name: 'creative' }
  | { name: 'resource'; title: string; path: string };

const RESOURCE_MAP: Partial<Record<ControlArea, { title: string; path: string }>> = {
  cm: { title: 'Content Management', path: '/api/cm/sections' },
  usage: { title: 'Usage & Credits', path: '/api/mobile/usage' },
  subscription: { title: 'Subscription', path: '/api/entitlements/me' },
  users: { title: 'Users', path: '/api/auth/users' },
  scheduled: { title: 'Scheduled', path: '/api/schedule/posts' },
  owner: { title: 'Owner Control Center', path: '/api/platform/metrics' },
};

export default function App() {
  const [screen, setScreen] = useState<Screen>({ name: 'boot' });
  const [isPlatformOwner, setIsPlatformOwner] = useState(false);

  useEffect(() => {
    (async () => {
      const access = await tokenStore.getAccessToken();
      const user = await tokenStore.getUser();
      setIsPlatformOwner(user?.role === 'platform_owner');
      setScreen(access ? { name: 'chat' } : { name: 'login' });
    })();
  }, []);

  async function afterLogin() {
    const user = await tokenStore.getUser();
    setIsPlatformOwner(user?.role === 'platform_owner');
    setScreen({ name: 'chat' });
  }

  async function logout() {
    await tokenStore.clear();
    setIsPlatformOwner(false);
    setScreen({ name: 'login' });
  }

  if (screen.name === 'boot') {
    return (
      <View style={styles.boot}>
        <ActivityIndicator color={colors.accent} />
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      {screen.name === 'login' ? (
        <LoginScreen onLoggedIn={() => void afterLogin()} onGoRegister={() => setScreen({ name: 'register' })} />
      ) : null}
      {screen.name === 'register' ? <RegisterScreen onBack={() => setScreen({ name: 'login' })} /> : null}
      {screen.name === 'chat' ? (
        <ChatScreen onOpenControlCenter={() => setScreen({ name: 'control' })} />
      ) : null}
      {screen.name === 'control' ? (
        <ControlCenterScreen
          isPlatformOwner={isPlatformOwner}
          onBack={() => setScreen({ name: 'chat' })}
          onOpen={(area) => {
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
            const target = RESOURCE_MAP[area];
            if (target) {
              setScreen({ name: 'resource', ...target });
            }
          }}
          onLogout={() => void logout()}
        />
      ) : null}
      {screen.name === 'settings' ? (
        <SettingsScreen onBack={() => setScreen({ name: 'control' })} onLogout={() => void logout()} />
      ) : null}
      {screen.name === 'integrations' ? (
        <IntegrationsScreen onBack={() => setScreen({ name: 'control' })} />
      ) : null}
      {screen.name === 'creative' ? (
        <CreativeStudioScreen onBack={() => setScreen({ name: 'control' })} />
      ) : null}
      {screen.name === 'resource' ? (
        <SimpleResourceScreen
          title={screen.title}
          path={screen.path}
          onBack={() => setScreen({ name: 'control' })}
        />
      ) : null}
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  boot: { flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center' },
});
