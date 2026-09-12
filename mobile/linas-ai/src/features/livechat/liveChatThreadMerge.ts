import { liveChatMessageFromSseData } from './liveChatSseParse';
import type { LiveChatMessage } from './liveChatTypes';

const LOCAL_PREFIX = 'local-';
const ECHO_WINDOW_MS = 120_000;

function messageId(msg: LiveChatMessage): string {
  return String(msg.message_id || '');
}

function isLocalMessage(msg: LiveChatMessage): boolean {
  return messageId(msg).startsWith(LOCAL_PREFIX);
}

export function hasPendingOperatorSend(rows: LiveChatMessage[]): boolean {
  return rows.some(
    (msg) =>
      isLocalMessage(msg) || msg.delivery_status === 'sending' || msg.delivery_status === 'failed',
  );
}

function preservedClientSendId(msg: LiveChatMessage): string {
  const client = String(msg.client_send_id || '').trim();
  if (client) return client;
  return isLocalMessage(msg) ? messageId(msg) : '';
}

function messageBody(msg: LiveChatMessage): string {
  return String(msg.content || msg.text || '').trim();
}

function timestampsClose(a?: string | null, b?: string | null): boolean {
  const left = Date.parse(String(a || ''));
  const right = Date.parse(String(b || ''));
  if (!Number.isFinite(left) || !Number.isFinite(right)) return false;
  return Math.abs(left - right) <= ECHO_WINDOW_MS;
}

function clientSendKey(msg: LiveChatMessage): string {
  return String(
    msg.client_send_id || msg.idempotency_key || (isLocalMessage(msg) ? messageId(msg) : '') || '',
  );
}

function deliveryStatusOf(msg: LiveChatMessage): string {
  return String(msg.delivery_status || '').trim();
}

/** Same outbound bubble the server persisted after an optimistic send. */
export function isOperatorEcho(local: LiveChatMessage, server: LiveChatMessage): boolean {
  if (local.is_user || server.is_user) return false;
  if (isLocalMessage(server)) return false;
  const localClient = clientSendKey(local);
  const serverClient = clientSendKey(server);
  if (localClient && serverClient && localClient === serverClient) return true;
  if (messageBody(local) !== messageBody(server)) return false;
  return timestampsClose(local.timestamp, server.timestamp);
}

function dedupeThreadMessages(rows: LiveChatMessage[]): LiveChatMessage[] {
  const seen = new Set<string>();
  const out: LiveChatMessage[] = [];
  for (const msg of rows) {
    const id = messageId(msg);
    const key =
      id && !id.startsWith(LOCAL_PREFIX)
        ? `id:${id}`
        : `loose:${msg.timestamp}|${messageBody(msg)}|${msg.is_user ? 1 : 0}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(msg);
  }
  return out;
}

function withPreservedDelivery(prev: LiveChatMessage, incoming: LiveChatMessage): LiveChatMessage {
  const incomingStatus = deliveryStatusOf(incoming);
  if (incomingStatus) {
    return {
      ...incoming,
      idempotency_key: incoming.idempotency_key || prev.idempotency_key,
      client_send_id: incoming.client_send_id || prev.client_send_id,
    };
  }
  const priorStatus = deliveryStatusOf(prev);
  if (!priorStatus) return incoming;
  return {
    ...incoming,
    delivery_status: priorStatus,
    delivery_error: incoming.delivery_error || prev.delivery_error,
    idempotency_key: incoming.idempotency_key || prev.idempotency_key,
    client_send_id: incoming.client_send_id || prev.client_send_id,
  };
}

/**
 * Poll merge: keep older pages, replace optimistic locals with the server echo,
 * keep sends newer than a stale poll window, and never flash a second copy.
 */
export function mergeThreadMessages(
  prev: LiveChatMessage[],
  incoming: LiveChatMessage[],
): LiveChatMessage[] {
  if (!prev.length) return dedupeThreadMessages(incoming);
  if (!incoming.length) return prev;

  const incomingIds = new Set(
    incoming.map(messageId).filter((id) => id && !id.startsWith(LOCAL_PREFIX)),
  );
  const claimed = new Set<number>();
  const keptLocals: LiveChatMessage[] = [];
  const echoClientIds = new Map<number, string>();
  const echoPrior = new Map<number, LiveChatMessage>();

  for (const prior of prev) {
    if (!isLocalMessage(prior)) continue;
    const match = incoming.findIndex((msg, index) => !claimed.has(index) && isOperatorEcho(prior, msg));
    if (match >= 0) {
      claimed.add(match);
      const clientId = clientSendKey(prior);
      if (clientId) echoClientIds.set(match, clientId);
      echoPrior.set(match, prior);
    } else {
      keptLocals.push(prior);
    }
  }

  const prevClientById = new Map<string, string>();
  const prevById = new Map<string, LiveChatMessage>();
  for (const prior of prev) {
    const id = messageId(prior);
    const clientId = preservedClientSendId(prior);
    if (id && !id.startsWith(LOCAL_PREFIX) && clientId) prevClientById.set(id, clientId);
    if (id) prevById.set(id, prior);
  }

  const incomingWithKeys = incoming.map((msg, index) => {
    const clientId = echoClientIds.get(index) || prevClientById.get(messageId(msg));
    const prior = echoPrior.get(index) || prevById.get(messageId(msg));
    const next = clientId
      ? { ...msg, client_send_id: clientId, idempotency_key: msg.idempotency_key || prior?.idempotency_key }
      : msg;
    return prior ? withPreservedDelivery(prior, next) : next;
  });

  const oldestIncoming = incoming[0]?.timestamp;
  const newestIncoming = incoming[incoming.length - 1]?.timestamp;
  const leftover = prev.filter((prior) => {
    if (isLocalMessage(prior)) return false;
    const id = messageId(prior);
    if (id && incomingIds.has(id)) return false;
    if (preservedClientSendId(prior)) return true;
    const ts = String(prior.timestamp || '');
    if (oldestIncoming && ts < String(oldestIncoming)) return true;
    if (newestIncoming && ts > String(newestIncoming)) return true;
    return false;
  });

  const merged = [...leftover, ...incomingWithKeys, ...keptLocals];
  merged.sort((a, b) => String(a.timestamp || '').localeCompare(String(b.timestamp || '')));
  return dedupeThreadMessages(merged);
}

export function applyMessageStatus(
  prev: LiveChatMessage[],
  data: Record<string, unknown>,
): LiveChatMessage[] {
  const status = String(data.delivery_status || '').trim();
  if (!status) return prev;
  const clientId = String(data.client_message_id || data.client_send_id || '').trim();
  const messageIdValue = String(data.message_id || '').trim();
  const error = data.error != null ? String(data.error) : undefined;
  let matched = false;
  const next = prev.map((msg) => {
    const msgClient = clientSendKey(msg);
    const hit =
      (clientId && (msgClient === clientId || messageId(msg) === clientId)) ||
      (messageIdValue && messageId(msg) === messageIdValue);
    if (!hit) return msg;
    matched = true;
    return {
      ...msg,
      delivery_status: status,
      delivery_error: status === 'failed' ? error || msg.delivery_error : undefined,
    };
  });
  return matched ? next : prev;
}

/** Append or replace one SSE message without dropping the rest of the open thread. */
export function mergeSseThreadMessage(
  prev: LiveChatMessage[],
  data: Record<string, unknown>,
): LiveChatMessage[] {
  const incoming = liveChatMessageFromSseData(data);
  if (!incoming || (!messageBody(incoming) && !incoming.message_id && data.delivery_status)) {
    return applyMessageStatus(prev, data);
  }
  return mergeThreadMessages(prev, [incoming]);
}
