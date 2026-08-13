import { registerRootComponent } from 'expo';
import * as SplashScreen from 'expo-splash-screen';

import App from './App';

// Hold the warm native splash until BootSplash mounts and calls hideAsync.
void SplashScreen.preventAutoHideAsync().catch(() => {
  // Non-fatal on web / Expo Go edge cases.
});

// registerRootComponent calls AppRegistry.registerComponent('main', () => App);
// It also ensures that whether you load the app in Expo Go or in a native build,
// the environment is set up appropriately
registerRootComponent(App);
