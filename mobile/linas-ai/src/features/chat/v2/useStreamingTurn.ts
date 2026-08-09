import { useCallback, useState } from 'react';

import type { StreamCard, StreamChoice } from './useOwnerStream';
import { useOwnerStream } from './useOwnerStream';

type Bootstrap = () => Promise<void> | void;

/**
 * Owns streaming UI state for one owner conversation turn.
 */
export function useStreamingTurn(conversationId: string | null, bootstrap: Bootstrap) {
  const stream = useOwnerStream();
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

  const send = useCallback(
    async (
      text: string,
      opts?: {
        choice_id?: string;
        choice_set_id?: string;
        attachment_ids?: string[];
        confirm_tool?: string | null;
      },
    ): Promise<'done' | 'error' | 'cancelled' | 'skipped'> => {
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
          onError: () => {
            resetUi();
            void bootstrap();
          },
          onCancelled: () => {
            resetUi();
            void bootstrap();
          },
          onDone: () => {
            resetUi();
            void bootstrap();
          },
        },
      );
      return result;
    },
    [bootstrap, conversationId, resetUi, stream],
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
