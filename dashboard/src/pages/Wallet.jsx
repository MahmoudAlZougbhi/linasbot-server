import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { authFetch } from '../utils/authFetch';
import { errorMessage } from '../utils/apiValidate';
import { useAuth } from '../contexts/AuthContext';

/** @param {number | string | null | undefined} n */
const formatTokens = (n) => Number(n || 0).toLocaleString();

/** @param {string} key */
const channelLabel = (key) => {
  /** @type {Record<string, string>} */
  const map = {
    facebook: 'Facebook',
    tiktok: 'TikTok',
    tiktok_comment: 'TikTok comments',
    tiktok_dm: 'TikTok',
    instagram: 'Instagram',
    testing_lab: 'Testing Lab',
    whatsapp: 'WhatsApp',
    unknown: 'Unknown',
    other: 'Other',
  };
  return map[key] || key;
};

const Wallet = () => {
  const { user } = /** @type {AuthContextValue} */ (useAuth());
  const [params] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [wallet, setWallet] = useState(/** @type {Record<string, unknown> | null} */ (null));
  const [packages, setPackages] = useState(/** @type {Array<Record<string, unknown>>} */ ([]));
  const [summary, setSummary] = useState('');
  const [stripeConfigured, setStripeConfigured] = useState(false);
  const [checkoutMsg, setCheckoutMsg] = useState('');
  const [buyingId, setBuyingId] = useState('');
  const [analytics, setAnalytics] = useState(/** @type {Record<string, unknown> | null} */ (null));

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
      if (typeof data.summary === 'string') setSummary(data.summary);
      const analyticsRes = await authFetch('/api/billing/wallet/analytics');
      const analyticsData = await analyticsRes.json();
      if (analyticsData?.success) setAnalytics(analyticsData);
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
  const inputRemaining = Number(wallet?.input_remaining ?? 0);
  const outputRemaining = Number(wallet?.output_remaining ?? 0);
  const inputUsed = Number(wallet?.input_used ?? wallet?.lifetime_input_debited ?? 0);
  const outputUsed = Number(wallet?.output_used ?? wallet?.lifetime_output_debited ?? 0);
  const spentUsd = Number(wallet?.lifetime_spent_usd ?? 0);
  const eitherEmpty = !unlimited && (inputRemaining <= 0 || outputRemaining <= 0);
  const policyText = typeof wallet?.policy === 'string' ? wallet.policy : '';

  /** @type {Record<string, unknown> | null} */
  const trailing = analytics?.periods && typeof analytics.periods === 'object'
    ? /** @type {Record<string, unknown>} */ (/** @type {Record<string, unknown>} */ (analytics.periods).trailing_12_months)
    : null;
  /** @type {Record<string, unknown> | null} */
  const prior = analytics?.periods && typeof analytics.periods === 'object'
    ? /** @type {Record<string, unknown>} */ (/** @type {Record<string, unknown>} */ (analytics.periods).prior_12_months)
    : null;

  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm text-slate-500">
          <Link to="/settings" className="font-medium text-primary-700 underline">
            Settings
          </Link>
          {' · '}
          Token Wallet
        </p>
        <h1 className="mt-1 font-display text-3xl font-bold text-slate-900">Token wallet</h1>
        <p className="mt-2 max-w-2xl text-slate-600">
          Prepaid input and output AI tokens for your workspace ({user?.tenantId || 'tenant'}).
          Each AI call uses input tokens for what the model reads and output tokens for what it writes.
          Detailed per-message spend and reasons are in{' '}
          <Link to="/content-managers" className="font-medium text-primary-700 underline">
            AI Setup
          </Link>
          .
        </p>
        {summary ? <p className="mt-2 text-sm text-slate-500">{summary}</p> : null}
        {policyText ? <p className="mt-1 text-xs text-slate-500">{policyText}</p> : null}
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
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div className="rounded-2xl border border-slate-200 bg-white/80 p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Input remaining</p>
            <p className="mt-2 text-2xl font-bold text-slate-900">
              {unlimited ? 'Unlimited' : formatTokens(inputRemaining)}
            </p>
            <p className="mt-1 text-xs text-slate-500">Used: {formatTokens(inputUsed)}</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white/80 p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Output remaining</p>
            <p className="mt-2 text-2xl font-bold text-slate-900">
              {unlimited ? 'Unlimited' : formatTokens(outputRemaining)}
            </p>
            <p className="mt-1 text-xs text-slate-500">Used: {formatTokens(outputUsed)}</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white/80 p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Paid (USD)</p>
            <p className="mt-2 text-2xl font-bold text-slate-900">${spentUsd.toFixed(2)}</p>
          </div>
        </div>
      )}

      {eitherEmpty && !loading && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          AI replies are paused until you recharge. Either the input or output balance is empty.
          FAQ-only answers that do not call the model may still work.
        </div>
      )}

      {!unlimited && (
        <section>
          <h2 className="text-xl font-semibold text-slate-900">Buy / recharge packages</h2>
          {!stripeConfigured && (
            <p className="mt-2 text-sm text-slate-600">
              Card checkout is not enabled on this server yet. Ask the owner to credit tokens, or configure Stripe.
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
                  <p className="font-display text-lg font-bold text-slate-900">
                    {String(pack.label || 'Token pack')}
                  </p>
                  <p className="mt-2 text-3xl font-bold text-primary-700">
                    ${Number(pack.sell_price_usd || 0).toFixed(2)}
                  </p>
                  <ul className="mt-3 space-y-1 text-sm text-slate-600">
                    <li>{formatTokens(/** @type {number|string|null|undefined} */ (pack.input_tokens))} input tokens</li>
                    <li>{formatTokens(/** @type {number|string|null|undefined} */ (pack.output_tokens))} output tokens</li>
                  </ul>
                  <button
                    type="button"
                    disabled={!stripeConfigured || buyingId === id}
                    onClick={() => buy(id)}
                    className="mt-4 w-full rounded-xl bg-gradient-to-r from-primary-600 to-secondary-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {buyingId === id ? 'Starting checkout…' : 'Buy / recharge'}
                  </button>
                </motion.div>
              );
            })}
          </div>
        </section>
      )}

      <section className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold text-slate-900">Spend analytics</h2>
            <p className="mt-1 text-sm text-slate-600">
              Aggregated from Interaction Logs. Per-message input/output tokens and $ are on each log entry.
            </p>
          </div>
          <Link to="/content-managers" className="text-sm font-medium text-primary-700 underline">
            Open AI Setup
          </Link>
        </div>

        {Array.isArray(analytics?.notes) && analytics.notes.length > 0 && (
          <ul className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
            {analytics.notes.map((note) => (
              <li key={String(note)}>{String(note)}</li>
            ))}
          </ul>
        )}

        <div className="grid gap-4 lg:grid-cols-2">
          {[trailing, prior].filter(Boolean).map((period) => {
            const p = /** @type {Record<string, unknown>} */ (period);
            const byChannel = /** @type {Record<string, Record<string, unknown>>} */ (p.by_channel || {});
            const top = Array.isArray(p.top_conversations) ? p.top_conversations : [];
            return (
              <div key={String(p.label)} className="rounded-2xl border border-slate-200 bg-white/90 p-5">
                <h3 className="font-semibold text-slate-900">{String(p.display_label || p.label)}</h3>
                <p className="mt-2 text-sm text-slate-600">
                  {formatTokens(/** @type {number|string|null|undefined} */ (p.tokens))} tokens · $
                  {Number(p.cost_usd || 0).toFixed(4)} recorded cost · {Number(p.interactions || 0)} interactions
                </p>
                {!p.cost_available && (
                  <p className="mt-1 text-xs text-amber-700">USD cost unavailable for this period.</p>
                )}
                <div className="mt-4 space-y-2">
                  {['facebook', 'instagram', 'tiktok', 'testing_lab', 'whatsapp', 'unknown'].map((key) => {
                    const row = byChannel[key];
                    if (!row || !Number(row.interactions || 0)) return null;
                    return (
                      <div key={key} className="flex justify-between text-sm text-slate-700">
                        <span>{channelLabel(key)}</span>
                        <span>
                          {formatTokens(/** @type {number|string|null|undefined} */ (row.tokens))} · $
                          {Number(row.cost_usd || 0).toFixed(4)}
                        </span>
                      </div>
                    );
                  })}
                </div>
                {top[0] && (
                  <p className="mt-4 text-sm text-slate-600">
                    Highest spend chat:{' '}
                    <span className="font-medium text-slate-900">
                      {String(/** @type {Record<string, unknown>} */ (top[0]).conversation_id)}
                    </span>{' '}
                    ({channelLabel(String(/** @type {Record<string, unknown>} */ (top[0]).channel || 'unknown'))})
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
};

export default Wallet;
