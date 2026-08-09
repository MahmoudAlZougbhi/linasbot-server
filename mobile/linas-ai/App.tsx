import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { tokenStore } from './src/auth/tokenStore';
import { LoginScreen } from './src/features/auth/LoginScreen';
import { RegisterScreen } from './src/features/auth/RegisterScreen';
import { ChatScreen } from './src/features/chat/ChatScreen';
import { ControlCenterScreen, type ControlArea } from './src/features/control/ControlCenterScreen';
import { SimpleResourceScreen } from './src/features/shared/SimpleResourceScreen';
import { colors } from './src/theme/colors';

type Screen =
  | { name: 'boot' }
  | { name: 'login' }
  | { name: 'register' }
  | { name: 'chat' }
  | { name: 'control' }
  | { name: 'resource'; title: string; path: string };

const RESOURCE_MAP: Record<ControlArea, { title: string; path: string } | null> = {
  create: { title: 'Creative Studio', path: '/api/entitlements/me' },
  cm: { title: 'Content Management', path: '/api/cm/sections' },
  integrations: { title: 'Integrations', path: '/api/mobile/integrations' },
  usage: { title: 'Usage & Credits', path: '/api/mobile/usage' },
  subscription: { title: 'Subscription', path: '/api/entitlements/me' },
  users: { title: 'Users', path: '/api/auth/session' },
  scheduled: { title: 'Scheduled', path: '/api/schedule/posts' },
  settings: { title: 'Settings', path: '/api/auth/session' },
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
      if (access) {
        setScreen({ name: 'chat' });
      } else {
        setScreen({ name: 'login' });
      }
    })();
  }, []);

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
        <LoginScreen
          onLoggedIn={async () => {
            const user = await tokenStore.getUser();
            setIsPlatformOwner(user?.role === 'platform_owner');
            setScreen({ name: 'chat' });
          }}
          onGoRegister={() => setScreen({ name: 'register' })}
          onGoForgot={() => setScreen({ name: 'login' })}
        />
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
            const target = RESOURCE_MAP[area];
            if (target) {
              setScreen({ name: 'resource', ...target });
            }
          }}
          onLogout={async () => {
            await tokenStore.clear();
            setScreen({ name: 'login' });
          }}
        />
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
