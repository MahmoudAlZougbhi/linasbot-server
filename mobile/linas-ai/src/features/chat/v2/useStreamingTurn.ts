import { useCallback, useEffect, useRef, useState } from 'react';

import type { StreamCard, StreamChoice } from './useOwnerStream';
import { useOwnerStream } from './useOwnerStream';

type TurnHooks = {
  onTerminal: () => Promise<void> | void;
  onTitleUpdated?: (title: string) => void;
};

/**
 * Owns streaming UI state for one owner conversation turn.
 */
export function useStreamingTurn(conversationId: string | null, hooks: TurnHooks) {
  const stream = useOwnerStream();
  const hooksRef = useRef(hooks);
  useEffect(() => {
    hooksRef.current = hooks;
  }, [hooks]);

  const [thinking, setThinking] = useState(false);
  const [statusRows, setStatusRows] = useState<{ id: string; text: string }[]>([]);
  const [liveText, setLiveText] = useState('');
  const [cards, setCards] = useState<StreamCard[]>([]);
  const [choices, setChoices] = useState<StreamChoice[]>([]);
  const [choiceSetId, setChoiceSetId] = useState<string | null>(null);

  const resetUi = useCallback(() => {
    setThinking(false);
    setStatusRows([]);
    setLiveText('');
  }, []);

  const applyTitle = useCallback((payload: Record<string, unknown> | string) => {
    const next =
      typeof payload === 'string'
        ? payload
        : String(payload.conversation_title || payload.title || '');
    if (next.trim()) hooksRef.current.onTitleUpdated?.(next.trim());
  }, []);

  const send = useCallback(
    async (
      text: string,
      opts?: {
        choice_id?: string;
        choice_set_id?: string;
        attachment_ids?: string[];
        confirm_tool?: string | null;
        owner_mode?: 'chat' | 'work';
      },
    ): Promise<'done' | 'error' | 'network_error' | 'cancelled' | 'skipped'> => {
      if (!conversationId) return 'skipped';
      resetUi();
      setCards([]);
      setChoices([]);
      setChoiceSetId(null);
      setThinking(true);
      const result = await stream.sendStream(
        conversationId,
        {
          content: text,
          choice_id: opts?.choice_id,
          choice_set_id: opts?.choice_set_id,
          attachment_ids: opts?.attachment_ids,
          confirm_tool: opts?.confirm_tool,
          owner_mode: opts?.owner_mode,
        },
        {
          onThinking: () => setThinking(true),
          onStatus: (s) => {
            setThinking(false);
            setStatusRows((prev) => [...prev.filter((p) => p.id !== s.id), s]);
          },
          onDelta: (t) => {
            setThinking(false);
            setLiveText((prev) => prev + t);
          },
          onCard: (c) => setCards((prev) => [...prev.filter((x) => x.id !== c.id), c]),
          onChoices: (p) => {
            setChoiceSetId(p.choice_set_id);
            setChoices(p.choices || []);
          },
          onTitleUpdated: (title) => applyTitle(title),
          onError: () => {
            resetUi();
            void hooksRef.current.onTerminal();
          },
          onCancelled: () => {
            resetUi();
            void hooksRef.current.onTerminal();
          },
          onDone: (payload) => {
            applyTitle(payload);
            resetUi();
            void hooksRef.current.onTerminal();
          },
        },
      );
      return result;
    },
    [applyTitle, conversationId, resetUi, stream],
  );

  return {
    send,
    stop: stream.stop,
    streaming: stream.streaming,
    thinking,
    statusRows,
    liveText,
    cards,
    choices,
    choiceSetId,
  };
}
