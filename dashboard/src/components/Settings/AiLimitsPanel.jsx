import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { authFetch } from '../../utils/authFetch';
import { errorMessage } from '../../utils/apiValidate';

/**
 * Settings → AI Limits panel (per end-user image + context-line quotas).
 * Kept outside Settings.jsx to avoid growing that file past the size limit.
 */
const AiLimitsPanel = () => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [recommended, setRecommended] = useState(/** @type {Record<string, unknown>} */ ({}));
  const [form, setForm] = useState({
    unlimited: false,
    image_per_day: 20,
    image_per_week: 100,
    context_lines_per_day: 500,
    context_lines_per_week: 2000,
    enforce_image_day: true,
    enforce_image_week: true,
    enforce_context_day: true,
    enforce_context_week: true,
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await authFetch('/api/settings/ai-limits');
      const data = await res.json();
      if (!data?.success) throw new Error(data?.error || 'Failed to load AI limits');
      const limits = data.limits || {};
      setRecommended(data.recommended || limits.recommended || {});
      setForm({
        unlimited: Boolean(limits.unlimited),
        image_per_day: Number(limits.image_per_day ?? 20),
        image_per_week: Number(limits.image_per_week ?? 100),
        context_lines_per_day: Number(limits.context_lines_per_day ?? 500),
        context_lines_per_week: Number(limits.context_lines_per_week ?? 2000),
        enforce_image_day: limits.enforce_image_day !== false,
        enforce_image_week: limits.enforce_image_week !== false,
        enforce_context_day: limits.enforce_context_day !== false,
        enforce_context_week: limits.enforce_context_week !== false,
      });
    } catch (err) {
      setError(errorMessage(err) || 'Could not load AI limits');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const applyRecommended = () => {
    setForm((prev) => ({
      ...prev,
      unlimited: false,
      image_per_day: Number(recommended.image_per_day ?? 20),
      image_per_week: Number(recommended.image_per_week ?? 100),
      context_lines_per_day: Number(recommended.context_lines_per_day ?? 500),
      context_lines_per_week: Number(recommended.context_lines_per_week ?? 2000),
      enforce_image_day: true,
      enforce_image_week: true,
      enforce_context_day: true,
      enforce_context_week: true,
    }));
  };

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const res = await authFetch('/api/settings/ai-limits', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ limits: form }),
      });
      const data = await res.json();
      if (!data?.success) throw new Error(data?.error || 'Save failed');
      toast.success('AI limits saved');
      await load();
    } catch (err) {
      setError(errorMessage(err) || 'Save failed');
      toast.error('Failed to save AI limits');
    } finally {
      setSaving(false);
    }
  };

  /** @param {string} key @param {unknown} value */
  const setField = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-900">AI Limits (per customer)</h3>
        <p className="mt-1 max-w-2xl text-sm text-slate-600">
          Cap how much AI each Messenger / Instagram / chat end-user may consume so one person cannot burn
          the whole token wallet. Recommended values are sensible starting points for a typical clinic —
          not Meta-approved quotas. Token wallet unlimited bypass does not disable these caps unless you
          turn on Unlimited below.
        </p>
        <p className="mt-2 text-sm text-slate-600">
          Also manage prepaid balances in{' '}
          <Link to="/wallet" className="font-medium text-primary-700 underline">
            Token Wallet
          </Link>
          .
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-slate-600">Loading AI limits…</p>
      ) : (
        <>
          <label className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
            <input
              type="checkbox"
              checked={form.unlimited}
              onChange={(e) => setField('unlimited', e.target.checked)}
              className="mt-1"
            />
            <span>
              <strong>Unlimited (not recommended).</strong> Disables per-customer image and context-line
              caps for this clinic. Token wallet metering is separate.
            </span>
          </label>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-white/90 p-5">
              <h4 className="font-semibold text-slate-900">Image analysis quota</h4>
              <p className="mt-1 text-xs text-slate-500">
                Max images the AI may analyze per end-user. Recommended: {Number(recommended.image_per_day ?? 20)}/day,{' '}
                {Number(recommended.image_per_week ?? 100)}/week.
              </p>
              <div className="mt-4 space-y-3">
                <label className="block text-sm">
                  Per day
                  <input
                    type="number"
                    min={0}
                    disabled={form.unlimited || !form.enforce_image_day}
                    value={form.image_per_day}
                    onChange={(e) => setField('image_per_day', Number(e.target.value))}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form.enforce_image_day}
                    disabled={form.unlimited}
                    onChange={(e) => setField('enforce_image_day', e.target.checked)}
                  />
                  Enforce daily image limit
                </label>
                <label className="block text-sm">
                  Per week
                  <input
                    type="number"
                    min={0}
                    disabled={form.unlimited || !form.enforce_image_week}
                    value={form.image_per_week}
                    onChange={(e) => setField('image_per_week', Number(e.target.value))}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form.enforce_image_week}
                    disabled={form.unlimited}
                    onChange={(e) => setField('enforce_image_week', e.target.checked)}
                  />
                  Enforce weekly image limit
                </label>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white/90 p-5">
              <h4 className="font-semibold text-slate-900">Context / knowledge lines</h4>
              <p className="mt-1 text-xs text-slate-500">
                Max non-empty lines of retrieved knowledge + message context the AI may read per end-user.
                Recommended: {Number(recommended.context_lines_per_day ?? 500)}/day,{' '}
                {Number(recommended.context_lines_per_week ?? 2000)}/week.
              </p>
              <div className="mt-4 space-y-3">
                <label className="block text-sm">
                  Per day
                  <input
                    type="number"
                    min={0}
                    disabled={form.unlimited || !form.enforce_context_day}
                    value={form.context_lines_per_day}
                    onChange={(e) => setField('context_lines_per_day', Number(e.target.value))}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form.enforce_context_day}
                    disabled={form.unlimited}
                    onChange={(e) => setField('enforce_context_day', e.target.checked)}
                  />
                  Enforce daily context-line limit
                </label>
                <label className="block text-sm">
                  Per week
                  <input
                    type="number"
                    min={0}
                    disabled={form.unlimited || !form.enforce_context_week}
                    value={form.context_lines_per_week}
                    onChange={(e) => setField('context_lines_per_week', Number(e.target.value))}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form.enforce_context_week}
                    disabled={form.unlimited}
                    onChange={(e) => setField('enforce_context_week', e.target.checked)}
                  />
                  Enforce weekly context-line limit
                </label>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={applyRecommended}
              className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800"
            >
              Apply recommended defaults
            </button>
            <button
              type="button"
              disabled={saving}
              onClick={save}
              className="rounded-xl bg-gradient-to-r from-primary-600 to-secondary-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save AI limits'}
            </button>
          </div>
        </>
      )}
    </div>
  );
};

export default AiLimitsPanel;
