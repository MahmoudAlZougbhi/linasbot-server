#!/usr/bin/env node
/**
 * Drives shipped public/web-chat/widget-runtime.js against live HTTP routes.
 * No duplicated createApi — only browser simulation (DOM, localStorage, fetch Origin).
 */
import {
  apiBase,
  widgetKey,
  origin,
  scenario,
  WidgetDriver,
  makeStorage,
  loadRuntime,
  createBrowserEnv,
  createBrowserFetch,
  waitFor,
  sleep,
} from './web_chat_widget_protocol_support.mjs';

if (!apiBase || !widgetKey) {
  console.error(JSON.stringify({ ok: false, error: 'missing_env' }));
  process.exit(1);
}

async function scenarioBootstrapFollowupAckReload() {
  const widget = await WidgetDriver.create(apiBase, widgetKey);
  await widget.openChat();
  if (!(process.env.WEB_CHAT_SESSION_ID && process.env.WEB_CHAT_SESSION_AUTHORITY)) {
    await widget.sendMessage('Hello acceptance');
  }
  await widget.tickPoll();
  await waitFor(() => widget.getMessages().some((m) => m.role === 'assistant'));
  const beforeAck = widget.getMessages();
  await widget.tickPoll();
  await sleep(80);
  await widget.tickPoll();
  const reloaded = await widget.reload(apiBase);
  await reloaded.openChat();
  await reloaded.tickPoll();
  const reloadMessages = reloaded.getMessages().filter((m) => m.role === 'assistant');
  const reloadIds = reloadMessages.map((m) => m.id).filter(Boolean);
  return {
    ok: true,
    scenario,
    session_id: widget.getStoredSession().session_id,
    assistant_before_reload: beforeAck.filter((m) => m.role === 'assistant').length,
    reload_assistant_messages: reloadMessages,
    reload_assistant_count: reloadMessages.length,
    reload_assistant_ids: reloadIds,
    reload_poll: reloadMessages,
  };
}

async function scenarioLostPollAck() {
  const widget = await WidgetDriver.create(apiBase, widgetKey, {
    fetchHooks: { failPollCount: 1, failAckCount: 1, ackDelayMs: 120 },
  });
  await widget.openChat();
  await sleep(80);
  await widget.tickPoll();
  const pollCountAfterLoss = widget.env.pollResponses.length;
  await widget.tickPoll();
  const successfulPolls = widget.env.pollResponses.filter((entry) => entry);
  const firstPollCount = pollCountAfterLoss === 0
    ? 0
    : (widget.env.pollResponses[pollCountAfterLoss - 1]?.messages || []).length;
  const retryPollCount = (successfulPolls[0]?.messages || []).length;
  await waitFor(() => widget.getMessages().some((m) => m.role === 'assistant'), { timeoutMs: 20000 });
  const preReloadAssistant = widget.getMessages().filter((m) => m.role === 'assistant');
  const preReloadIds = preReloadAssistant.map((m) => m.id).filter(Boolean);
  await sleep(250);
  await widget.tickPoll();
  const afterPoll = widget.env.pollResponses[widget.env.pollResponses.length - 1];
  const afterAckCount = (afterPoll?.messages || []).length;
  const ackRequests = widget.env.sandbox.fetch.ackRequests || [];
  const reloaded = await widget.reload(apiBase);
  await reloaded.openChat();
  await reloaded.tickPoll();
  const reloadMessages = reloaded.getMessages().filter((m) => m.role === 'assistant');
  const reloadIds = reloadMessages.map((m) => m.id).filter(Boolean);
  const uniqueReloadIds = [...new Set(reloadIds)];
  const delivered = preReloadAssistant.length === 1 && preReloadIds.length === 1;
  const stableIdMerge = reloadIds.length === 1 && reloadIds[0] === preReloadIds[0];
  const noDuplicateInsertion = reloadMessages.length === 1 && uniqueReloadIds.length === 1;
  const idempotentAck = ackRequests.length <= 2
    && ackRequests.every((ids) => ids.length <= 1)
    && (ackRequests.length === 0 || ackRequests[0][0] === preReloadIds[0]);
  return {
    ok: delivered && retryPollCount >= 1 && afterAckCount === 0 && stableIdMerge && noDuplicateInsertion && idempotentAck,
    scenario,
    first_poll_count: firstPollCount,
    retry_poll_count: retryPollCount,
    after_ack_count: afterAckCount,
    reload_assistant_count: reloadMessages.length,
    pre_reload_assistant_ids: preReloadIds,
    reload_assistant_ids: reloadIds,
    ack_requests: ackRequests,
    message_ids: preReloadIds,
  };
}

async function scenarioRepeatedAckFailureRecovery() {
  const widget = await WidgetDriver.create(apiBase, widgetKey, {
    fetchHooks: { failAckCount: 3 },
  });
  await widget.openChat();
  await sleep(80);
  await widget.tickPoll();
  await waitFor(() => widget.getMessages().some((m) => m.role === 'assistant'), { timeoutMs: 20000 });
  const assistant = widget.getMessages().filter((m) => m.role === 'assistant');
  const assistantIds = assistant.map((m) => m.id).filter(Boolean);
  for (let i = 0; i < 6; i += 1) {
    await widget.tickPoll();
    await sleep(80);
  }
  const ackRequests = widget.env.sandbox.fetch.ackRequests || [];
  const ackAttempts = widget.env.sandbox.fetch.ackAttempts || [];
  const afterPoll = widget.env.pollResponses[widget.env.pollResponses.length - 1];
  const afterAckCount = (afterPoll?.messages || []).length;
  const followupAssistant = assistant.filter((m) => m.content === 'Node harness follow-up');
  return {
    ok:
      followupAssistant.length === 1
      && assistantIds.length >= 1
      && ackAttempts.length >= 4
      && ackRequests.length >= 1
      && afterAckCount === 0
      && ackAttempts.every((ids) => ids.length <= 1),
    scenario,
    assistant_ids: assistantIds,
    ack_requests: ackRequests,
    ack_attempts: ackAttempts,
    after_ack_count: afterAckCount,
    followup_assistant_count: followupAssistant.length,
  };
}

async function scenarioTwoWidgetsSamePrefix() {
  const prefix = widgetKey.slice(0, 12);
  const keyA = `${prefix}aaaaaaaaaaaa`;
  const keyB = `${prefix}bbbbbbbbbbbb`;
  const sharedStorage = makeStorage();
  const runtimeProbe = loadRuntime(createBrowserEnv({ fetchImpl: createBrowserFetch({ origin }) }).sandbox);
  const digestA = runtimeProbe.widgetStorageDigest(keyA);
  const digestB = runtimeProbe.widgetStorageDigest(keyB);
  if (digestA === digestB) {
    return { ok: false, scenario, error: 'digest_collision' };
  }

  const widgetA = await WidgetDriver.create(apiBase, keyA, { localStorage: sharedStorage });
  await widgetA.openChat();
  const sessionA = widgetA.getStoredSession();

  const widgetB = await WidgetDriver.create(apiBase, keyB, { localStorage: sharedStorage });
  await widgetB.openChat();
  const sessionB = widgetB.getStoredSession();

  const reloadedA = await widgetA.reload(apiBase);
  await reloadedA.openChat();
  const sessionAAfterReload = reloadedA.getStoredSession();
  const reloadedB = await widgetB.reload(apiBase);
  await reloadedB.openChat();
  const sessionBAfterReload = reloadedB.getStoredSession();

  const dump = sharedStorage._dump();
  const idA = dump[sessionA.sessionIdKey] || '';
  const idB = dump[sessionB.sessionIdKey] || '';
  const crossRead =
    sessionAAfterReload.session_id === sessionB.session_id ||
    sessionBAfterReload.session_id === sessionA.session_id;
  const overwrite = idA !== sessionA.session_id || idB !== sessionB.session_id;

  return {
    ok:
      sessionA.session_id &&
      sessionB.session_id &&
      sessionA.session_id !== sessionB.session_id &&
      sessionAAfterReload.session_id === sessionA.session_id &&
      sessionBAfterReload.session_id === sessionB.session_id &&
      !crossRead &&
      !overwrite,
    scenario,
    prefix,
    session_a: sessionA.session_id,
    session_b: sessionB.session_id,
    digest_a: digestA,
    digest_b: digestB,
    storage_keys: Object.keys(dump),
    shared_prefix_collision: false,
    cross_read: crossRead,
    overwrite,
  };
}

async function main() {
  let result;
  if (scenario === 'bootstrap_followup_ack_reload') {
    result = await scenarioBootstrapFollowupAckReload();
  } else if (scenario === 'lost_poll_ack') {
    result = await scenarioLostPollAck();
  } else if (scenario === 'repeated_ack_failure_recovery') {
    result = await scenarioRepeatedAckFailureRecovery();
  } else if (scenario === 'two_widgets_same_prefix') {
    result = await scenarioTwoWidgetsSamePrefix();
  } else {
    result = { ok: false, error: 'unknown_scenario', scenario };
  }
  console.log(JSON.stringify(result));
}

main().catch((err) => {
  console.error(JSON.stringify({ ok: false, error: String(err), scenario }));
  process.exit(1);
});
