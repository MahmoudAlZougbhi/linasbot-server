import { useCallback, useEffect, useRef, useState } from 'react';

import { API_BASE } from '../../../api/client';
import { appendLocalFile } from '../../../api/formDataFile';
import { tokenStore } from '../../../auth/tokenStore';

export type StreamStatus = { id: string; text: string };
export type StreamCard = {
  id: string;
  kind: string;
  title: string;
  body?: string;
  status?: string;
  data?: Record<string, unknown>;
};
export type StreamChoice = {
  id: string;
  label: string;
  action: string;
  payload?: Record<string, unknown>;
};

type StreamHandlers = {
  onThinking?: () => void;
  onStatus?: (status: StreamStatus) => void;
  onDelta?: (text: string) => void;
  onCard?: (card: StreamCard) => void;
  onChoices?: (payload: { choice_set_id: string; choices: StreamChoice[] }) => void;
  onTitleUpdated?: (title: string) => void;
  onError?: (message: string) => void;
  onDone?: (payload: Record<string, unknown>) => void;
  onCancelled?: () => void;
};

function dispatchEvent(raw: string, handlers: StreamHandlers) {
  let ev: Record<string, unknown>;
  try {
    ev = JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return;
  }
  const type = String(ev.type || '');
  if (type === 'thinking') handlers.onThinking?.();
  else if (type === 'status') {
    handlers.onStatus?.({ id: String(ev.id || ''), text: String(ev.text || '') });
  } else if (type === 'delta') handlers.onDelta?.(String(ev.text || ''));
  else if (type === 'card' && ev.card) handlers.onCard?.(ev.card as StreamCard);
  else if (type === 'choices') {
    handlers.onChoices?.({
      choice_set_id: String(ev.choice_set_id || ''),
      choices: (ev.choices as StreamChoice[]) || [],
    });
  } else if (type === 'title_updated') {
    handlers.onTitleUpdated?.(String(ev.title || ''));
  } else if (type === 'error') handlers.onError?.(String(ev.message || 'error'));
  else if (type === 'cancelled') handlers.onCancelled?.();
  else if (type === 'done') handlers.onDone?.(ev);
}

/**
 * True SSE consumer for Owner Copilot V2 (XHR progressive — works on React Native).
 * Does not animate a completed response; applies server deltas as the buffer grows.
 */
export function useOwnerStream() {
  const xhrRef = useRef<XMLHttpRequest | null>(null);
  const notifyCancelRef = useRef(false);
  const [streaming, setStreaming] = useState(false);

  const abortActive = useCallback((notifyCancel: boolean) => {
    notifyCancelRef.current = notifyCancel;
    const xhr = xhrRef.current;
    xhrRef.current = null;
    if (xhr) xhr.abort();
    else setStreaming(false);
    if (notifyCancel) setStreaming(false);
  }, []);

  const stop = useCallback(() => {
    abortActive(true);
  }, [abortActive]);

  const sendStream = useCallback(
    (
      conversationId: string,
      body: {
        content?: string;
        confirm_tool?: string | null;
        tool_args?: Record<string, unknown>;
        choice_id?: string;
        choice_set_id?: string;
        attachment_ids?: string[];
      },
      handlers: StreamHandlers,
    ): Promise<'done' | 'error' | 'network_error' | 'cancelled'> => {
      // Replace any in-flight stream quietly (do not fire onCancelled for the new turn).
      abortActive(false);
      return (async () => {
        const access = await tokenStore.getAccessToken();
        if (!access) {
          handlers.onError?.('Not authenticated');
          return 'error' as const;
        }

        setStreaming(true);
        const xhr = new XMLHttpRequest();
        xhrRef.current = xhr;
        let seen = 0;
        let carry = '';
        let terminal: 'done' | 'error' | 'network_error' | 'cancelled' = 'done';
        let settled = false;

        return await new Promise<'done' | 'error' | 'network_error' | 'cancelled'>((resolve) => {
          const finish = (result: 'done' | 'error' | 'network_error' | 'cancelled') => {
            if (settled) return;
            settled = true;
            if (xhrRef.current === xhr) {
              xhrRef.current = null;
              setStreaming(false);
            }
            resolve(result);
          };

          xhr.open(
            'POST',
            `${API_BASE}/api/owner-ai/conversations/${conversationId}/messages/stream`,
          );
          xhr.setRequestHeader('Authorization', `Bearer ${access}`);
          xhr.setRequestHeader('Accept', 'text/event-stream');
          xhr.setRequestHeader('Content-Type', 'application/json');

          xhr.onprogress = () => {
            const chunk = xhr.responseText.slice(seen);
            seen = xhr.responseText.length;
            carry += chunk;
            const parts = carry.split('\n\n');
            carry = parts.pop() || '';
            for (const part of parts) {
              const line = part
                .split('\n')
                .map((l) => l.trim())
                .find((l) => l.startsWith('data:'));
              if (!line) continue;
              const raw = line.slice(5).trim();
              try {
                const evType = String((JSON.parse(raw) as { type?: string }).type || '');
                if (evType === 'error') terminal = 'error';
                else if (evType === 'cancelled') terminal = 'cancelled';
                else if (evType === 'done') terminal = 'done';
              } catch {
                /* ignore parse for terminal tracking */
              }
              dispatchEvent(raw, handlers);
            }
          };

          xhr.onerror = () => {
            handlers.onError?.('stream_network_error');
            finish('network_error');
          };

          xhr.onabort = () => {
            if (notifyCancelRef.current) {
              notifyCancelRef.current = false;
              handlers.onCancelled?.();
            }
            finish('cancelled');
          };

          xhr.onload = () => {
            if (carry.trim()) {
              const line = carry
                .split('\n')
                .map((l) => l.trim())
                .find((l) => l.startsWith('data:'));
              if (line) {
                const raw = line.slice(5).trim();
                try {
                  const evType = String((JSON.parse(raw) as { type?: string }).type || '');
                  if (evType === 'error') terminal = 'error';
                  else if (evType === 'cancelled') terminal = 'cancelled';
                  else if (evType === 'done') terminal = 'done';
                } catch {
                  /* ignore */
                }
                dispatchEvent(raw, handlers);
              }
            }
            if (xhr.status >= 400) {
              handlers.onError?.(`stream_http_${xhr.status}`);
              finish('error');
              return;
            }
            finish(terminal);
          };

          xhr.send(JSON.stringify(body));
        });
      })();
    },
    [abortActive],
  );

  useEffect(() => () => abortActive(false), [abortActive]);

  return { sendStream, stop, streaming };
}

export async function uploadOwnerAttachment(file: {
  uri: string;
  name: string;
  mimeType: string;
}): Promise<{ attachment_id: string; filename: string; mime: string; size: number }> {
  const access = await tokenStore.getAccessToken();
  if (!access) throw new Error('Not authenticated');
  const form = new FormData();
  // Expo SDK 57 fetch rejects RN { uri, name, type } FormData parts.
  appendLocalFile(form, 'file', file.uri, { name: file.name });
  const res = await fetch(`${API_BASE}/api/owner-ai/v2/attachments`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${access}`, Accept: 'application/json' },
    body: form,
  });
  const data = (await res.json()) as Record<string, unknown>;
  if (!res.ok || !data.success) {
    throw new Error(String(data.detail || data.error || 'upload_failed'));
  }
  return {
    attachment_id: String(data.attachment_id),
    filename: String(data.filename),
    mime: String(data.mime),
    size: Number(data.size || 0),
  };
}
