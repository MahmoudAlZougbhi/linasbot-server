import { useEffect, useRef, useState } from 'react';
import { ownerApi } from './ownerApi';

/** @typedef {{ role: 'user' | 'assistant' | 'status', text: string }} BrainLine */

/**
 * @param {{
 *   title: string,
 *   messages: BrainLine[],
 *   draft: string,
 *   setDraft: (value: string) => void,
 *   onSend: () => void,
 *   busy: boolean,
 *   disabled: boolean,
 *   disabledReason: string,
 * }} props
 */
function BrainColumn({ title, messages, draft, setDraft, onSend, busy, disabled, disabledReason }) {
  return (
    <section className="flex min-h-[32rem] flex-col rounded-xl border border-slate-800 bg-slate-950">
      <header className="border-b border-slate-800 px-4 py-3">
        <h3 className="font-semibold">{title}</h3>
      </header>
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <p className="text-sm text-slate-500">No messages yet. The reply comes from this tenant&apos;s published brain.</p>
        )}
        {messages.map((line, index) => (
          <p
            key={`${line.role}-${index}`}
            className={
              line.role === 'user'
                ? 'ml-8 rounded-lg bg-teal-500/15 px-3 py-2 text-sm'
                : line.role === 'status'
                  ? 'text-sm text-amber-200'
                  : 'mr-8 rounded-lg bg-slate-900 px-3 py-2 text-sm'
            }
          >
            {line.text}
          </p>
        ))}
      </div>
      <form
        className="flex gap-2 border-t border-slate-800 p-3"
        onSubmit={(event) => {
          event.preventDefault();
          onSend();
        }}
      >
        <input
          aria-label={`Message ${title}`}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          disabled={disabled || busy}
          className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
          placeholder="Write a message"
        />
        <button
          type="submit"
          aria-label={`Send to ${title}`}
          disabled={disabled || busy || !draft.trim()}
          title={disabled ? disabledReason : busy ? 'A reply is in progress' : !draft.trim() ? 'Write a message first' : 'Send'}
          className="rounded-lg bg-teal-500 px-3 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40"
        >
          {busy ? 'Sending…' : 'Send'}
        </button>
      </form>
    </section>
  );
}

export default function OwnerBrains() {
  const [subscribers, setSubscribers] = useState(/** @type {OwnerSubscriber[]} */ ([]));
  const [loadingTenants, setLoadingTenants] = useState(true);
  const [draftMode, setDraftMode] = useState(false);
  const [tenantId, setTenantId] = useState('');
  const [error, setError] = useState('');
  const [customer, setCustomer] = useState(/** @type {BrainLine[]} */ ([]));
  const [copilot, setCopilot] = useState(/** @type {BrainLine[]} */ ([]));
  const [customerDraft, setCustomerDraft] = useState('');
  const [copilotDraft, setCopilotDraft] = useState('');
  const [busy, setBusy] = useState('');
  const tenantRef = useRef(tenantId);
  tenantRef.current = tenantId;

  useEffect(() => {
    let live = true;
    ownerApi.subscribers()
      .then((data) => {
        if (!live) return;
        const rows = data.subscribers || [];
        setSubscribers(rows);
        if (rows[0]?.tenant_id) setTenantId(rows[0].tenant_id);
      })
      .catch((reason) => live && setError(reason.message))
      .finally(() => live && setLoadingTenants(false));
    return () => { live = false; };
  }, []);

  /** @param {string} next */
  const chooseTenant = (next) => {
    setTenantId(next);
    setCustomer([]);
    setCopilot([]);
    setCustomerDraft('');
    setCopilotDraft('');
    setError('');
    setBusy('');
  };

  /**
   * @param {'customer' | 'copilot'} brain
   * @param {BrainLine[]} thread
   * @param {string} draft
   * @param {(lines: BrainLine[]) => void} setThread
   * @param {(value: string) => void} setDraft
   */
  const send = async (brain, thread, draft, setThread, setDraft) => {
    const message = draft.trim();
    if (!tenantId || !message || busy) return;
    const startedTenant = tenantId;
    setBusy(brain);
    setError('');
    setDraft('');
    const history = thread
      .filter((line) => line.role === 'user' || line.role === 'assistant')
      .map((line) => ({ role: line.role, text: line.text }));
    setThread([...thread, { role: 'user', text: message }]);
    try {
      const data = await ownerApi.brainTurn(brain, {
        tenant_id: startedTenant,
        message,
        history,
        mode: brain === 'customer' && draftMode ? 'draft' : 'live',
      });
      if (tenantRef.current !== startedTenant) return;
      /** @type {BrainLine[]} */
      const extra = [];
      if (data.reply) extra.push({ role: 'assistant', text: data.reply });
      if (data.hint) extra.push({ role: 'status', text: data.hint });
      else if (!data.reply && data.reason) extra.push({ role: 'status', text: `Status: ${data.reason}` });
      if (data.pending_confirmation) extra.push({ role: 'status', text: `Waiting for approval: ${data.pending_confirmation}` });
      if (!extra.length) extra.push({ role: 'status', text: 'Status: no reply' });
      setThread([...thread, { role: 'user', text: message }, ...extra]);
    } catch (reason) {
      if (tenantRef.current !== startedTenant) return;
      setThread([...thread, { role: 'user', text: message }, { role: 'status', text: reason instanceof Error ? reason.message : 'Request failed' }]);
    } finally {
      if (tenantRef.current === startedTenant) setBusy('');
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">Brains</h2>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">
          Talk to the customer brain and the owner copilot using one tenant&apos;s published setup.
          This desk does not spend that tenant&apos;s messages. A customer-brain order or appointment
          is saved on the tenant under a lab customer.
        </p>
      </header>
      <label className="block max-w-xl text-sm">
        <span className="text-slate-400">Tenant</span>
        <select
          aria-label="Tenant"
          value={tenantId}
          onChange={(event) => chooseTenant(event.target.value)}
          className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2"
        >
          {loadingTenants && <option value="">Loading tenants…</option>}
          {!loadingTenants && subscribers.length === 0 && <option value="">No tenants yet. Create one from the app.</option>}
          {subscribers.map((row) => (
            <option key={row.tenant_id} value={row.tenant_id}>
              {row.business_name || row.email || row.tenant_id}
            </option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-2 text-sm text-slate-300">
        <input type="checkbox" checked={draftMode} onChange={(event) => setDraftMode(event.target.checked)} />
        Test draft (unpublished customer brain)
      </label>
      {error && <p role="alert" className="rounded-lg bg-red-950 p-3 text-red-200">{error}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        <BrainColumn
          title="Customer brain"
          messages={customer}
          draft={customerDraft}
          setDraft={setCustomerDraft}
          busy={busy === 'customer'}
          disabled={!tenantId || busy === 'copilot'}
          disabledReason={loadingTenants ? 'Tenants are still loading' : 'Choose a tenant first'}
          onSend={() => send('customer', customer, customerDraft, setCustomer, setCustomerDraft)}
        />
        <BrainColumn
          title="Owner copilot"
          messages={copilot}
          draft={copilotDraft}
          setDraft={setCopilotDraft}
          busy={busy === 'copilot'}
          disabled={!tenantId || busy === 'customer'}
          disabledReason={loadingTenants ? 'Tenants are still loading' : 'Choose a tenant first'}
          onSend={() => send('copilot', copilot, copilotDraft, setCopilot, setCopilotDraft)}
        />
      </div>
    </div>
  );
}
