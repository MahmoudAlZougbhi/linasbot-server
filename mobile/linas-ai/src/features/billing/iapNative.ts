import { Platform } from 'react-native';

/**
 * Lazy-load react-native-iap so Expo Go / web / Android typecheck paths
 * do not crash on missing Nitro native modules.
 *
 * Types are intentionally loose: package exports point at .ts source which
 * breaks tsc (missing `global`). Runtime require stays iOS-only.
 */
export type IapModule = {
  ErrorCode: { UserCancelled: string; [key: string]: string };
  initConnection: () => Promise<unknown>;
  fetchProducts: (args: {
    skus: string[];
    type: 'in-app' | 'subs';
  }) => Promise<Array<{ id: string; displayPrice?: string; currency?: string }> | null | void>;
  requestPurchase: (args: {
    type: 'in-app' | 'subs';
    request: { apple?: { sku: string; appAccountToken?: string } };
  }) => Promise<unknown>;
  finishTransaction: (args: {
    purchase: unknown;
    isConsumable?: boolean;
  }) => Promise<unknown>;
  getAvailablePurchases: () => Promise<
    Array<{ productId: string; purchaseToken?: string | null }> | null | void
  >;
  purchaseUpdatedListener: (
    listener: (purchase: {
      productId: string;
      ids?: string[] | null;
      purchaseToken?: string | null;
      id: string;
    }) => void,
  ) => { remove: () => void };
  purchaseErrorListener: (
    listener: (error: { code: string; message?: string | null }) => void,
  ) => { remove: () => void };
  beginRefundRequestIOS?: (sku: string) => Promise<unknown>;
  showManageSubscriptionsIOS?: () => Promise<unknown>;
  deepLinkToSubscriptionsIOS?: () => Promise<unknown>;
};

let cached: IapModule | null | undefined;

export function loadIapModule(): IapModule | null {
  if (cached !== undefined) return cached;
  if (Platform.OS !== 'ios') {
    cached = null;
    return null;
  }
  try {
    // Native module only exists in dev client / production iOS builds.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    cached = require('react-native-iap') as IapModule;
    return cached;
  } catch {
    cached = null;
    return null;
  }
}

export function isIapNativeAvailable(): boolean {
  return loadIapModule() != null;
}
