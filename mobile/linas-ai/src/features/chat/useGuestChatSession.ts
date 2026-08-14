import { useCallback, useEffect, useState } from 'react';

import { ApiError } from '../../api/client';
import { isNetworkFailure } from '../../api/networkError';
import { ensureGuestSession, sendGuestMessage } from '../../api/guestClient';
import type { ChatMessage } from '../../api/types';
import { getOrCreateGuestSessionId } from '../../auth/guestSession';
import { useI18n } from '../../i18n/LanguageContext';

function clearGuestState(
  setGuestId: (v: string | null) => void,
  setMessages: (v: ChatMessage[]) => void,
  setGated: (v: boolean) => void,
  setGateText: (v: string | null) => void,
) {
  setGuestId(null);
  setMessages([]);
  setGated(false);
  setGateText(null);
}

export function useGuestChatSession(enabled = true) {
  const { language, tr } = useI18n();
  const [guestId, setGuestId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(enabled);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gated, setGated] = useState(false);
  const [gateText, setGateText] = useState<string | null>(null);

  const bootstrap = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      clearGuestState(setGuestId, setMessages, setGated, setGateText);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const id = await getOrCreateGuestSessionId();
      setGuestId(id);
      const session = await ensureGuestSession(id, language);
      setMessages(session.messages);
      setGated(Boolean(session.limit_reached));
    } catch {
      setError('retry');
    } finally {
      setLoading(false);
    }
  }, [enabled, language]);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  async function send(
    content: string,
  ): Promise<'done' | 'gated' | 'rejected' | 'error' | 'network_error' | 'skipped'> {
    if (!guestId || !content.trim() || gated) {
      return 'skipped';
    }
    setSending(true);
    setError(null);
    const body = content.trim();
    setMessages((prev) => [
      ...prev,
      {
        id: `local-${Date.now()}`,
        role: 'user',
        content: body,
        created_at: Date.now() / 1000,
      },
    ]);
    try {
      const result = await sendGuestMessage(guestId, body, language);
      if (!result.ok) {
        setGated(true);
        const msg =
          result.gateMessages?.[language] ||
          result.gateMessages?.en ||
          tr('guestLimitReached');
        setGateText(msg);
        setMessages(result.session.messages);
        return 'gated';
      }
      setMessages(result.session.messages);
      if (result.session.limit_reached) {
        setGated(true);
        setGateText(tr('guestLimitReached'));
      }
      return 'done';
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        const code = String(err.message || '');
        if (code === 'GUEST_INPUT_TOO_LARGE' || code === 'input_token_limit') {
          setError('guestInputTooLarge');
        } else if (code === 'GUEST_MEDIA_BLOCKED' || code === 'guest_media_blocked') {
          setError('guestMediaBlocked');
        } else {
          setError('guestWordLimit');
        }
      } else if (err instanceof ApiError && err.status === 503) {
        setError('guestModelUnavailable');
      } else if (isNetworkFailure(err)) {
        setError(null);
      } else if (err instanceof ApiError) {
        setError('messageFailed');
      } else {
        setError('messageFailed');
      }
      try {
        const session = await ensureGuestSession(guestId, language);
        setMessages(session.messages);
        setGated(Boolean(session.limit_reached));
      } catch {
        setMessages((prev) => prev.filter((m) => !String(m.id).startsWith('local-')));
      }
      return isNetworkFailure(err) ? 'network_error' : 'error';
    } finally {
      setSending(false);
    }
  }

  return {
    title: 'Linas AI',
    guestId,
    messages,
    loading,
    sending,
    error,
    gated,
    gateText,
    bootstrap,
    send,
    setError,
  };
}
