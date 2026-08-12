import { Linking, Platform } from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import {
  appleProductIdForPlan,
  isAppleCreditProduct,
  type BillingPeriod,
  type CreditPackId,
  APPLE_CREDIT_PRODUCTS,
} from './appleProductIds';
import { loadIapModule, type IapModule } from './iapNative';
import type { PlanId } from './planCatalog';

export type IapPurchaseResult =
  | { ok: true }
  | { ok: false; code: 'cancel' | 'unavailable' | 'verify_failed' | 'error'; message?: string };

/** Minimal purchase shape used after StoreKit listener events. */
type StorePurchase = {
  id: string;
  productId: string;
  ids?: string[] | null;
  purchaseToken?: string | null;
  [key: string]: unknown;
};

const AppAccountTokenSchema = z
  .object({
    success: z.boolean().optional(),
    app_account_token: z.string().uuid().optional(),
    appAccountToken: z.string().uuid().optional(),
  })
  .passthrough();

const VerifySchema = z.object({ success: z.boolean() }).passthrough();

const MANAGE_SUBSCRIPTIONS_URL = 'https://apps.apple.com/account/subscriptions';

let connectionReady = false;

export async function ensureIapConnection(): Promise<boolean> {
  if (Platform.OS !== 'ios') return false;
  const iap = loadIapModule();
  if (!iap) return false;
  if (connectionReady) return true;
  await iap.initConnection();
  connectionReady = true;
  return true;
}

async function fetchAppAccountToken(): Promise<string | null> {
  const data = await apiFetch('/api/entitlements/apple/app-account-token', {
    schema: AppAccountTokenSchema,
  });
  return data.app_account_token ?? data.appAccountToken ?? null;
}

function signedTransactionFromPurchase(purchase: {
  purchaseToken?: string | null;
}): string | null {
  const token = purchase.purchaseToken;
  return typeof token === 'string' && token.length > 10 ? token : null;
}

async function verifyOnServer(signedTransaction: string, appAccountToken: string | null) {
  await apiFetch('/api/entitlements/apple/verify', {
    method: 'POST',
    body: JSON.stringify({
      signed_transaction: signedTransaction,
      ...(appAccountToken ? { app_account_token: appAccountToken } : {}),
    }),
    schema: VerifySchema,
  });
}

function waitForPurchase(
  iap: IapModule,
  productId: string,
): Promise<{ purchase: StorePurchase; error?: never } | { purchase?: never; error: IapPurchaseResult }> {
  return new Promise((resolve) => {
    const ErrorCode = iap.ErrorCode;
    let settled = false;
    const finish = (
      result: { purchase: StorePurchase } | { error: IapPurchaseResult },
    ) => {
      if (settled) return;
      settled = true;
      updateSub.remove();
      errorSub.remove();
      resolve(result as never);
    };

    const updateSub = iap.purchaseUpdatedListener((purchase) => {
      if (purchase.productId !== productId && !(purchase.ids ?? []).includes(productId)) {
        return;
      }
      finish({ purchase: purchase as StorePurchase });
    });

    const errorSub = iap.purchaseErrorListener((error) => {
      if (error.code === ErrorCode.UserCancelled) {
        finish({ error: { ok: false, code: 'cancel' } });
        return;
      }
      finish({
        error: {
          ok: false,
          code: 'error',
          message: error.message || String(error.code),
        },
      });
    });
  });
}

async function purchaseSku(
  productId: string,
  type: 'subs' | 'in-app',
  isConsumable: boolean,
): Promise<IapPurchaseResult> {
  if (Platform.OS !== 'ios') {
    return { ok: false, code: 'unavailable', message: 'ios_only' };
  }
  const iap = loadIapModule();
  if (!iap) {
    return { ok: false, code: 'unavailable', message: 'native_iap_unavailable' };
  }

  try {
    await ensureIapConnection();
    const appAccountToken = await fetchAppAccountToken();
    const pending = waitForPurchase(iap, productId);
    await iap.requestPurchase({
      type,
      request: {
        apple: {
          sku: productId,
          ...(appAccountToken ? { appAccountToken } : {}),
        },
      },
    });
    const outcome = await pending;
    if ('error' in outcome && outcome.error) return outcome.error;

    const purchase = outcome.purchase!;
    const signed = signedTransactionFromPurchase(purchase);
    if (!signed) {
      return { ok: false, code: 'verify_failed', message: 'missing_signed_transaction' };
    }

    try {
      await verifyOnServer(signed, appAccountToken);
    } catch (err) {
      return {
        ok: false,
        code: 'verify_failed',
        message: err instanceof Error ? err.message : 'verify_failed',
      };
    }

    await iap.finishTransaction({
      purchase,
      isConsumable,
    });
    return { ok: true };
  } catch (err) {
    const code = (err as { code?: string })?.code;
    if (code === 'user-cancelled' || code === iap.ErrorCode?.UserCancelled) {
      return { ok: false, code: 'cancel' };
    }
    return {
      ok: false,
      code: 'error',
      message: err instanceof Error ? err.message : 'purchase_failed',
    };
  }
}

export async function purchaseSubscription(
  planId: PlanId,
  period: BillingPeriod,
): Promise<IapPurchaseResult> {
  return purchaseSku(appleProductIdForPlan(planId, period), 'subs', false);
}

export async function purchaseCredits(credits: CreditPackId): Promise<IapPurchaseResult> {
  return purchaseSku(APPLE_CREDIT_PRODUCTS[credits], 'in-app', true);
}

export async function restorePurchases(): Promise<IapPurchaseResult> {
  if (Platform.OS !== 'ios') {
    return { ok: false, code: 'unavailable', message: 'ios_only' };
  }
  const iap = loadIapModule();
  if (!iap) {
    return { ok: false, code: 'unavailable', message: 'native_iap_unavailable' };
  }

  try {
    await ensureIapConnection();
    const purchases = (await iap.getAvailablePurchases()) ?? [];
    const signedTransactions = purchases
      .map((p) => signedTransactionFromPurchase(p))
      .filter((t): t is string => Boolean(t));

    if (!signedTransactions.length) {
      return { ok: false, code: 'error', message: 'no_purchases' };
    }

    await apiFetch('/api/entitlements/apple/restore', {
      method: 'POST',
      body: JSON.stringify({ signed_transactions: signedTransactions }),
      schema: VerifySchema,
    });

    for (const purchase of purchases) {
      const consumable = isAppleCreditProduct(purchase.productId);
      try {
        await iap.finishTransaction({ purchase, isConsumable: consumable });
      } catch {
        // Already finished / not finishable — ignore.
      }
    }
    return { ok: true };
  } catch (err) {
    return {
      ok: false,
      code: 'error',
      message: err instanceof Error ? err.message : 'restore_failed',
    };
  }
}

export async function openManageSubscriptions(): Promise<void> {
  if (Platform.OS === 'ios') {
    const iap = loadIapModule();
    try {
      if (iap?.showManageSubscriptionsIOS) {
        await iap.showManageSubscriptionsIOS();
        return;
      }
      if (iap?.deepLinkToSubscriptionsIOS) {
        await iap.deepLinkToSubscriptionsIOS();
        return;
      }
    } catch {
      // Fall through to App Store URL.
    }
  }
  await Linking.openURL(MANAGE_SUBSCRIPTIONS_URL);
}

/** Present StoreKit refund request sheet for a product SKU (iOS 15+). */
export async function requestRefundForProduct(sku: string): Promise<IapPurchaseResult> {
  if (Platform.OS !== 'ios') {
    return { ok: false, code: 'unavailable', message: 'ios_only' };
  }
  const iap = loadIapModule();
  if (!iap?.beginRefundRequestIOS) {
    return { ok: false, code: 'unavailable', message: 'refund_unavailable' };
  }
  try {
    await ensureIapConnection();
    await iap.beginRefundRequestIOS(sku);
    return { ok: true };
  } catch (err) {
    const code = (err as { code?: string })?.code;
    if (code === 'user-cancelled' || code === iap.ErrorCode?.UserCancelled) {
      return { ok: false, code: 'cancel' };
    }
    return {
      ok: false,
      code: 'error',
      message: err instanceof Error ? err.message : 'refund_failed',
    };
  }
}
