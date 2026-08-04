import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { authFetch } from '../utils/authFetch';
import { errorMessage } from '../utils/apiValidate';
import { useAuth } from '../contexts/AuthContext';

/** @param {number | string | null | undefined} n */
const formatTokens = (n) => Number(n || 0).toLocaleString();

const Wallet = () => {
  const { user } = /** @type {AuthContextValue} */ (useAuth());
  const [params] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [wallet, setWallet] = useState(/** @type {Record<string, unknown> | null} */ (null));
  const [packages, setPackages] = useState(/** @type {Array<Record<string, unknown>>} */ ([]));
  const [stripeConfigured, setStripeConfigured] = useState(false);
  const [basis, setBasis] = useState('');
  const [checkoutMsg, setCheckoutMsg] = useState('');
  const [buyingId, setBuyingId] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await authFetch('/api/billing/wallet');
      const data = await response.json();
      if (!data?.success) {
        throw new Error(data?.error || 'Failed to load wallet');
      }
      setWallet(data.wallet || null);
      setPackages(Array.isArray(data.packages) ? data.packages : []);
      setStripeConfigured(Boolean(data.stripe_configured));
      const pkgRes = await fetch('/api/billing/packages', { credentials: 'include' });
      const pkgData = await pkgRes.json();
      if (typeof pkgData?.basis === 'string') setBasis(pkgData.basis);
      if (Array.isArray(pkgData?.packages) && pkgData.packages.length) {
        setPackages(pkgData.packages);
      }
    } catch (err) {
      setError(errorMessage(err) || 'Could not load wallet');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const status = params.get('checkout');
    if (status === 'success') setCheckoutMsg('Checkout completed. Tokens appear after Stripe confirms payment.');
    if (status === 'cancel') setCheckoutMsg('Checkout canceled. No charge was made.');
  }, [params]);

  /** @param {string} packageId */
  const buy = async (packageId) => {
    setBuyingId(packageId);
    setError('');
    try {
      const response = await authFetch('/api/billing/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ package_id: packageId }),
      });
      const data = await response.json();
      if (!data?.success) {
        throw new Error(data?.error || 'Checkout unavailable');
      }
      if (typeof data.checkout_url === 'string' && data.checkout_url) {
        window.location.href = data.checkout_url;
        return;
      }
      throw new Error('Checkout URL missing');
    } catch (err) {
      setError(errorMessage(err) || 'Checkout failed');
    } finally {
      setBuyingId('');
    }
  };

  const unlimited = Boolean(wallet?.unlimited);
  const remaining = Number(wallet?.tokens_remaining ?? wallet?.balance_tokens ?? 0);
  const used = Number(wallet?.tokens_used ?? wallet?.lifetime_debited ?? 0);
  const spentUsd = Number(wallet?.lifetime_spent_usd ?? 0);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-3xl font-bold text-slate-900">Token wallet</h1>
        <p className="mt-2 max-w-2xl text-slate-600">
          Prepaid AI tokens for your workspace ({user?.tenantId || 'tenant'}). Usage matches Interaction Logs token counts.
        </p>
        {basis && <p className="mt-2 text-xs text-slate-500">{basis}</p>}
      </div>

      {checkoutMsg && (
        <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900" role="status">
          {checkoutMsg}
        </div>
      )}
      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-slate-600">Loading wallet…</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-2xl border border-slate-200 bg-white/80 p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Remaining</p>
            <p className="mt-2 text-2xl font-bold text-slate-900">
              {unlimited ? 'Unlimited' : formatTokens(remaining)}
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white/80 p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Used</p>
            <p className="mt-2 text-2xl font-bold text-slate-900">{formatTokens(used)}</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white/80 p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Spent (USD)</p>
            <p className="mt-2 text-2xl font-bold text-slate-900">${spentUsd.toFixed(2)}</p>
          </div>
        </div>
      )}

      {!unlimited && remaining <= 0 && !loading && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          AI replies are paused until you recharge. FAQ-only answers that do not call the model may still work.
        </div>
      )}

      {!unlimited && (
        <section>
          <h2 className="text-xl font-semibold text-slate-900">Recharge packages</h2>
          {!stripeConfigured && (
            <p className="mt-2 text-sm text-slate-600">
              Card checkout is not enabled on this server yet (set <code>STRIPE_SECRET_KEY</code>). Ask the owner to credit tokens, or configure Stripe.
            </p>
          )}
          <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {packages.map((pack) => {
              const id = String(pack.id || '');
              return (
                <motion.div
                  key={id}
                  whileHover={{ y: -2 }}
                  className="rounded-2xl border border-slate-200 bg-white/90 p-5 shadow-sm"
                >
                  <p className="font-display text-lg font-bold text-slate-900">{String(pack.label || `${pack.tokens} tokens`)}</p>
                  <p className="mt-2 text-3xl font-bold text-primary-700">${Number(pack.sell_price_usd || 0).toFixed(2)}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    ${Number(pack.price_per_1k_usd || 0).toFixed(4)} / 1k tokens · ~{Number(pack.margin_pct || 0).toFixed(0)}% margin
                  </p>
                  <button
                    type="button"
                    disabled={!stripeConfigured || buyingId === id}
                    onClick={() => buy(id)}
                    className="mt-4 w-full rounded-xl bg-gradient-to-r from-primary-600 to-secondary-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {buyingId === id ? 'Starting checkout…' : 'Buy with Stripe'}
                  </button>
                </motion.div>
              );
            })}
          </div>
        </section>
      )}

      <p className="text-sm text-slate-500">
        <Link to="/app" className="font-medium text-primary-700 underline">
          Back to dashboard
        </Link>
      </p>
    </div>
  );
};

export default Wallet;
