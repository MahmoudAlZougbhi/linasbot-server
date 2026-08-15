import { useCallback, useState } from 'react';

import { useI18n } from '../../i18n/LanguageContext';
import type { CreditPackId } from './appleProductIds';
import { purchaseCredits } from './iapPurchases';
import { useBillingStorePrices } from './useBillingData';

export function useBuyCreditsFlow(onPurchased?: () => void) {
  const { tr, language } = useI18n();
  const locale = language === 'ar' ? 'ar' : language === 'fr' ? 'fr' : 'en';
  const store = useBillingStorePrices('monthly', locale);
  const [open, setOpen] = useState(false);
  const [purchasing, setPurchasing] = useState(false);

  const buy = useCallback(
    async (credits: CreditPackId) => {
      if (purchasing) return;
      setPurchasing(true);
      store.setPurchaseNote(tr('subPurchasePending'));
      try {
        const result = await purchaseCredits(credits);
        if (result.ok) {
          store.setPurchaseNote(tr('subCreditsPurchaseSuccess'));
          setOpen(false);
          onPurchased?.();
        } else if (result.code === 'cancel') {
          store.setPurchaseNote(tr('subPurchaseCanceled'));
        } else if (result.code === 'unavailable') {
          store.setPurchaseNote(tr('subStoreUnavailable'));
        } else if (result.code === 'verify_failed') {
          store.setPurchaseNote(tr('subPurchaseVerifyFailed'));
        } else {
          store.setPurchaseNote(tr('subPurchaseError'));
        }
      } finally {
        setPurchasing(false);
      }
    },
    [onPurchased, purchasing, store, tr],
  );

  return {
    open,
    setOpen,
    prices: store.creditPrices,
    purchasing,
    locale,
    tr,
    buy,
    purchaseNote: store.purchaseNote,
  };
}
