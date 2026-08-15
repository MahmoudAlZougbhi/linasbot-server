import * as SecureStore from 'expo-secure-store';

/**
 * Default WHEN_UNLOCKED can reject at process start on iOS
 * (`errSecInteractionNotAllowed`) before UI is ready — looks like a logout.
 */
export const SECURE_STORE_OPTIONS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK,
};
