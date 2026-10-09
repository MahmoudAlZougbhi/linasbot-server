// @ts-nocheck
import { useEffect, useState } from 'react';
import { ownerApi } from './ownerApi';
import PageHeader from './ui/PageHeader';
import Card from './ui/Card';
import Button from './ui/Button';
import Alert from './ui/Alert';
import TechDetails from './ui/TechDetails';

const emptyBand = { min_tokens: 0, max_tokens: '', messages: 1 };

export default function OwnerCopilotPricing() {
  const [policy, setPolicy] = useState(null);
  const [note, setNote] = useState('');
  const [preview, setPreview] = useState('');
  const [history, setHistory] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState('');

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [current, past] = await Promise.all([ownerApi.copilotPricing(), ownerApi.copilotPricingHistory()]);
      setPolicy(current.policy);
      setPreview(String(current.preview_messages ?? ''));
      setHistory(past.history || []);
    } catch (err) {
      setError(err?.message || 'Could not load Copilot pricing.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function updateBand(index, field, value) {
    setPolicy((current) => {
      const bands = current.token_bands.map((row, rowIndex) => (rowIndex === index ? { ...row, [field]: value } : row));
      return { ...current, token_bands: bands };
    });
  }

  async function save() {
    setSaving(true);
    setSaved('');
    setError('');
    try {
      const body = {
        ...policy,
        note,
        token_bands: policy.token_bands.map((row) => ({
          min_tokens: Number(row.min_tokens),
          max_tokens: row.max_tokens === '' || row.max_tokens == null ? null : Number(row.max_tokens),
          messages: Number(row.messages),
        })),
      };
      const response = await ownerApi.saveCopilotPricing(body);
      setSaved(response.message || 'Pricing live now');
      setNote('');
      await load();
    } catch (err) {
      setError(err?.message || 'Could not save pricing.');
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p className="p-6">Loading Copilot pricing…</p>;
  if (!policy) return <Alert title={error || 'Copilot pricing is unavailable.'} />;

  return (
    <div className="space-y-4">
      <PageHeader title="Copilot pricing" subtitle="Choose how many messages a Copilot request uses." />
      {error ? <Alert title={error} /> : null}
      {saved ? <p className="text-sm text-teal-800">{saved}</p> : null}
      <Card>
        {policy.token_bands.map((row, index) => (
          <div key={`${index}`} className="mb-3 grid gap-2 md:grid-cols-3">
            <label className="text-sm">
              From tokens
              <input className="mt-1 w-full rounded border px-2 py-1" value={row.min_tokens} onChange={(event) => updateBand(index, 'min_tokens', event.target.value)} />
            </label>
            <label className="text-sm">
              To tokens (blank means and above)
              <input className="mt-1 w-full rounded border px-2 py-1" value={row.max_tokens ?? ''} onChange={(event) => updateBand(index, 'max_tokens', event.target.value)} />
            </label>
            <label className="text-sm">
              Messages
              <input className="mt-1 w-full rounded border px-2 py-1" value={row.messages} onChange={(event) => updateBand(index, 'messages', event.target.value)} />
            </label>
          </div>
        ))}
        <Button type="button" onClick={() => setPolicy({ ...policy, token_bands: [...policy.token_bands, emptyBand] })}>
          Add range
        </Button>
      </Card>
      <Card>
        <label className="block text-sm">
          Minimum messages per request
          <input className="mt-1 w-full rounded border px-2 py-1" value={policy.min_messages_per_request} onChange={(event) => setPolicy({ ...policy, min_messages_per_request: Number(event.target.value) })} />
        </label>
        <label className="mt-3 block text-sm">
          Maximum messages per request
          <input className="mt-1 w-full rounded border px-2 py-1" value={policy.max_messages_per_request} onChange={(event) => setPolicy({ ...policy, max_messages_per_request: Number(event.target.value) })} />
        </label>
        <label className="mt-3 block text-sm">
          Approval required above
          <input className="mt-1 w-full rounded border px-2 py-1" value={policy.approval_threshold_messages} onChange={(event) => setPolicy({ ...policy, approval_threshold_messages: Number(event.target.value) })} />
        </label>
        <p className="mt-3 text-sm">25,000 tokens uses {preview || 'not calculated'} messages after the minimum and maximum.</p>
        <label className="mt-3 block text-sm">
          Change note
          <input className="mt-1 w-full rounded border px-2 py-1" value={note} onChange={(event) => setNote(event.target.value)} />
        </label>
        <div className="mt-3">
          <Button type="button" disabled={saving || !note.trim()} loading={saving} onClick={save}>
            Save
          </Button>
        </div>
      </Card>
      <TechDetails text={history.length === 0 ? 'No pricing changes yet.' : history.map((row) => row.note).join('\n')} />
    </div>
  );
}
