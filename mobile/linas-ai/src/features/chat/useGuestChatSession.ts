import { useCallback, useEffect, useState } from 'react';

import { ApiError } from '../../api/client';
import { isNetworkFailure } from '../../api/networkError';
import { ensureGuestSession, sendGuestMessage } from '../../api/guestClient';
import type { ChatMessage } from '../../api/types';
import { getOrCreateGuestSessionId } from '../../auth/guestSession';
import { useI18n } from '../../i18n/LanguageContext';

export function useGuestChatSession(enabled = true) {
  const { language, tr } = useI18n();
  const [guestId, setGuestId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(enabled);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [questionsUsed, setQuestionsUsed] = useState(0);
  const [questionsRemaining, setQuestionsRemaining] = useState(10);
  const [maxQuestions, setMaxQuestions] = useState(10);
  const [maxWords, setMaxWords] = useState(50);
  const [gated, setGated] = useState(false);
  const [gateText, setGateText] = useState<string | null>(null);

  const bootstrap = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const id = await getOrCreateGuestSessionId();
      setGuestId(id);
      const session = await ensureGuestSession(id, language);
      setMessages(session.messages);
      setQuestionsUsed(session.questions_used);
      setQuestionsRemaining(session.questions_remaining);
      setMaxQuestions(session.max_questions);
      setMaxWords(session.max_words);
      setGated(session.questions_remaining <= 0);
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
    // Server enforces word ceiling (raised for V2); client does not invent a 50-word gate.
    if (maxWords > 0) {
      const words = content.trim().split(/\s+/).filter(Boolean).length;
      if (words > maxWords) {
        setError('guestWordLimit');
        return 'rejected';
      }
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
      setQuestionsUsed(result.session.questions_used);
      setQuestionsRemaining(result.session.questions_remaining);
      setMaxQuestions(result.session.max_questions);
      setMaxWords(result.session.max_words);
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
      if (result.session.questions_remaining <= 0) {
        setGated(true);
        setGateText(tr('guestLimitReached'));
      }
      return 'done';
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setError('guestWordLimit');
      } else if (err instanceof ApiError && err.status === 503) {
        // Honest model-down signal — do not invent a canned assistant bubble.
        setError('guestModelUnavailable');
      } else if (isNetworkFailure(err)) {
        setError(null);
      } else if (err instanceof ApiError) {
        setError('messageFailed');
      } else {
        setError('messageFailed');
      }
      // Drop optimistic user bubble and resync from server (LLM failures must not fake a reply).
      try {
        const session = await ensureGuestSession(guestId, language);
        setMessages(session.messages);
        setQuestionsUsed(session.questions_used);
        setQuestionsRemaining(session.questions_remaining);
        setMaxQuestions(session.max_questions);
        setMaxWords(session.max_words);
        setGated(session.questions_remaining <= 0);
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
    messages,
    loading,
    sending,
    error,
    questionsUsed,
    questionsRemaining,
    maxQuestions,
    maxWords,
    gated,
    gateText,
    bootstrap,
    send,
    setError,
  };
}
