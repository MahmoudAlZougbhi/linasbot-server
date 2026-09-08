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
 * and never flash a second copy of the message just sent.
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

  for (const prior of prev) {
    if (!isLocalMessage(prior)) continue;
    const match = incoming.findIndex((msg, index) => !claimed.has(index) && isOperatorEcho(prior, msg));
    if (match >= 0) {
      claimed.add(match);
    } else {
      keptLocals.push(prior);
    }
  }

  const oldestIncoming = incoming[0]?.timestamp;
  const older = prev.filter((prior) => {
    if (isLocalMessage(prior)) return false;
    const id = messageId(prior);
    if (id && incomingIds.has(id)) return false;
    if (!oldestIncoming) return false;
    return String(prior.timestamp || '') < String(oldestIncoming);
  });

  const merged = [...older, ...incoming, ...keptLocals];
  merged.sort((a, b) => String(a.timestamp || '').localeCompare(String(b.timestamp || '')));
  return dedupeThreadMessages(merged);
}
