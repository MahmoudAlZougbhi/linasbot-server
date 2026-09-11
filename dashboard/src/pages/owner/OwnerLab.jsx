import { useState } from 'react';
import { ownerApi } from './ownerApi';

function parseHistory(raw) {
  const text = raw.trim();
  if (!text) return undefined;
  const parsed = JSON.parse(text);
  if (!Array.isArray(parsed)) throw new Error('history must be a JSON array');
  return parsed;
}

export default function OwnerLab() {
  const [tenantId, setTenantId] = useState('lab');
  const [conversationId, setConversationId] = useState('lab:conv');
  const [userId, setUserId] = useState('lab:user');
  const [channel, setChannel] = useState('web_chat');
  const [messageId, setMessageId] = useState('');
  const [history, setHistory] = useState('');
  const [message, setMessage] = useState('');
  const [turn, setTurn] = useState(/** @type {any} */ (null));
  const [evals, setEvals] = useState(/** @type {any} */ (null));
  const [index, setIndex] = useState(/** @type {any} */ (null));
  const [classify, setClassify] = useState(/** @type {any} */ (null));
  const [generated, setGenerated] = useState(false);
  const [faqUsed, setFaqUsed] = useState(false);
  const [followupSent, setFollowupSent] = useState(false);
  const [error, setError] = useState('');

  async function runTurn() {
    setError('');
    try {
      const result = await ownerApi.labTurn({
        tenant_id: tenantId.trim() || 'lab',
        message,
        conversation_id: conversationId.trim() || 'lab:conv',
        user_id: userId.trim() || 'lab:user',
        channel: channel.trim() || 'web_chat',
        message_id: messageId.trim(),
        history: parseHistory(history),
      });
      setTurn(result);
      if (result?.ok === false) {
        const reason = String(result.reason || 'lab_turn_failed');
        if (reason === 'brain_disabled') {
          setError('Brain disabled: set CUSTOMER_BRAIN_ENABLED=true and LINAS_CUSTOMER_AI_LAB=true on staging.');
        } else if (reason === 'lab_disabled') {
          setError('Lab API disabled: set LINAS_CUSTOMER_AI_LAB=true on staging.');
        } else {
          setError(reason);
        }
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function runEvals() {
    setError('');
    try {
      setEvals(await ownerApi.labEvals());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function runClassify() {
    setError('');
    try {
      setClassify(
        await ownerApi.labClassify({
          generated,
          faq_used: faqUsed,
          followup_sent: followupSent,
        }),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function runReindex() {
    setError('');
    try {
      setIndex(await ownerApi.reindexTenant(tenantId.trim() || 'lab'));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  return (
    <div className="space-y-7">
      <header>
        <h2 className="text-2xl font-semibold">Customer Brain lab</h2>
        <p className="mt-1 text-sm text-slate-400">
          Capture-only. Requires LINAS_CUSTOMER_AI_LAB=true and CUSTOMER_BRAIN_ENABLED=true on staging,
          plus a lab / lab_* tenant. No live channel send. Force reindex needs published CM content.
          Conversation, channel, and inbound id are for confirmation and request-source checks.
        </p>
      </header>
      {error ? (
        <p role="alert" className="rounded-lg bg-red-950 p-3 text-sm text-red-200">
          {error}
        </p>
      ) : null}
      <section className="space-y-3 rounded-xl border border-slate-800 bg-slate-900 p-5">
        <input
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
          value={tenantId}
          onChange={(event) => setTenantId(event.target.value)}
          placeholder="lab tenant id"
        />
        <input
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
          value={conversationId}
          onChange={(event) => setConversationId(event.target.value)}
          placeholder="conversation id"
        />
        <input
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
          value={userId}
          onChange={(event) => setUserId(event.target.value)}
          placeholder="customer / user id"
        />
        <input
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
          value={channel}
          onChange={(event) => setChannel(event.target.value)}
          placeholder="channel (web_chat, instagram_dm, whatsapp)"
        />
        <input
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
          value={messageId}
          onChange={(event) => setMessageId(event.target.value)}
          placeholder="inbound message id"
        />
        <textarea
          className="h-20 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
          value={history}
          onChange={(event) => setHistory(event.target.value)}
          placeholder='Optional history JSON: [{"id":"m1","role":"user","text":"hi"}]'
        />
        <textarea
          className="h-28 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="Customer message"
        />
        <div className="flex gap-2">
          <button type="button" onClick={() => void runTurn()} className="rounded bg-teal-500 px-3 py-2 text-slate-950">
            Run turn
          </button>
          <button type="button" onClick={() => void runEvals()} className="rounded border border-slate-600 px-3 py-2">
            Run fixture evals
          </button>
          <button type="button" onClick={() => void runReindex()} className="rounded border border-slate-600 px-3 py-2">
            Force reindex
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-sm text-slate-300">
          <label>
            <input type="checkbox" checked={generated} onChange={(event) => setGenerated(event.target.checked)} /> generated
          </label>
          <label>
            <input type="checkbox" checked={faqUsed} onChange={(event) => setFaqUsed(event.target.checked)} /> faq used
          </label>
          <label>
            <input
              type="checkbox"
              checked={followupSent}
              onChange={(event) => setFollowupSent(event.target.checked)}
            />{' '}
            follow-up sent
          </label>
          <button type="button" onClick={() => void runClassify()} className="rounded border border-slate-600 px-3 py-1">
            Classify units
          </button>
        </div>
      </section>
      {turn ? (
        <pre className="overflow-auto rounded-xl border border-slate-800 bg-slate-950 p-4 text-xs text-slate-300">
          {JSON.stringify(turn, null, 2)}
        </pre>
      ) : null}
      {evals ? (
        <pre className="overflow-auto rounded-xl border border-slate-800 bg-slate-950 p-4 text-xs text-slate-300">
          {JSON.stringify(evals, null, 2)}
        </pre>
      ) : null}
      {index ? (
        <pre className="overflow-auto rounded-xl border border-slate-800 bg-slate-950 p-4 text-xs text-slate-300">
          {JSON.stringify(index, null, 2)}
        </pre>
      ) : null}
      {classify ? (
        <pre className="overflow-auto rounded-xl border border-slate-800 bg-slate-950 p-4 text-xs text-slate-300">
          {JSON.stringify(classify, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}
