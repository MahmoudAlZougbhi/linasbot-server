import type { LiveChatMessage } from './liveChatTypes';

const LOCAL_PREFIX = 'local-';
const ECHO_WINDOW_MS = 120_000;

function messageId(msg: LiveChatMessage): string {
  return String(msg.message_id || '');
}

function isLocalMessage(msg: LiveChatMessage): boolean {
  return messageId(msg).startsWith(LOCAL_PREFIX);
}

function messageBody(msg: LiveChatMessage): string {
  return String(msg.content || msg.text || '');
}

function timestampsClose(a?: string | null, b?: string | null): boolean {
  const left = Date.parse(String(a || ''));
  const right = Date.parse(String(b || ''));
  if (!Number.isFinite(left) || !Number.isFinite(right)) return false;
  return Math.abs(left - right) <= ECHO_WINDOW_MS;
}

/** Same outbound bubble the server persisted after an optimistic send. */
export function isOperatorEcho(local: LiveChatMessage, server: LiveChatMessage): boolean {
  if (local.is_user || server.is_user) return false;
  if (isLocalMessage(server)) return false;
  if (messageBody(local) !== messageBody(server)) return false;
  return timestampsClose(local.timestamp, server.timestamp);
}

function clientSendKey(msg: LiveChatMessage): string {
  return String(msg.client_send_id || (isLocalMessage(msg) ? messageId(msg) : '') || '');
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

/**
 * Poll merge: keep older pages, replace optimistic locals with the server echo,
 * keep sends newer than a stale poll window, and never flash a second copy.
 */
export function mergeThreadMessages(
  prev: LiveChatMessage[],
  incoming: LiveChatMessage[],
): LiveChatMessage[] {
  if (!prev.length) return incoming;
  if (!incoming.length) return prev;

  const incomingIds = new Set(
    incoming.map(messageId).filter((id) => id && !id.startsWith(LOCAL_PREFIX)),
  );
  const claimed = new Set<number>();
  const keptLocals: LiveChatMessage[] = [];
  const echoClientIds = new Map<number, string>();

  for (const prior of prev) {
    if (!isLocalMessage(prior)) continue;
    const match = incoming.findIndex((msg, index) => !claimed.has(index) && isOperatorEcho(prior, msg));
    if (match >= 0) {
      claimed.add(match);
      const clientId = clientSendKey(prior);
      if (clientId) echoClientIds.set(match, clientId);
    } else {
      keptLocals.push(prior);
    }
  }

  const incomingWithKeys = incoming.map((msg, index) => {
    const clientId = echoClientIds.get(index);
    return clientId ? { ...msg, client_send_id: clientId } : msg;
  });

  const oldestIncoming = incoming[0]?.timestamp;
  const newestIncoming = incoming[incoming.length - 1]?.timestamp;
  const leftover = prev.filter((prior) => {
    if (isLocalMessage(prior)) return false;
    const id = messageId(prior);
    if (id && incomingIds.has(id)) return false;
    const ts = String(prior.timestamp || '');
    if (oldestIncoming && ts < String(oldestIncoming)) return true;
    if (newestIncoming && ts > String(newestIncoming)) return true;
    return false;
  });

  const merged = [...leftover, ...incomingWithKeys, ...keptLocals];
  merged.sort((a, b) => String(a.timestamp || '').localeCompare(String(b.timestamp || '')));
  return dedupeThreadMessages(merged);
}
