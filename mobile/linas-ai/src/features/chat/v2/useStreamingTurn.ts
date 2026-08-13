import { useCallback, useEffect, useRef, useState } from 'react';

import {
  ownerModeFromStreamRoute,
  ownerModeFromStreamStatus,
} from '../ownerModeFromStream';
import { looksLikeOwnerAssent, pendingTokenFromDonePayload } from './ownerAssent';
import type { StreamCard, StreamChoice } from './useOwnerStream';
import { useOwnerStream } from './useOwnerStream';

type TurnHooks = {
  onTerminal: (opts?: { expectReplyText?: string }) => Promise<boolean> | boolean | void;
  onTitleUpdated?: (title: string) => void;
  /** Sync LIN chip when stream reports High / CM tools (never auto-downgrades). */
  onOwnerModeHint?: (mode: 'chat' | 'work') => void;
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
  const pendingConfirmRef = useRef<string | null>(null);

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
        tool_args?: Record<string, unknown>;
        revise_proposal_id?: string | null;
        owner_mode?: 'chat' | 'work';
        reply_language?: 'en' | 'ar' | 'fr';
      },
    ): Promise<'done' | 'error' | 'network_error' | 'cancelled' | 'skipped'> => {
      if (!conversationId) return 'skipped';
      resetUi();
      setCards([]);
      setChoices([]);
      setChoiceSetId(null);
      setThinking(true);
      let confirmTool = opts?.confirm_tool ?? null;
      const reviseId = opts?.revise_proposal_id?.trim() || null;
      // Edit-chip revision must not auto-approve via assent shortcut.
      if (!confirmTool && !reviseId && looksLikeOwnerAssent(text) && pendingConfirmRef.current) {
        confirmTool = pendingConfirmRef.current;
      }
      const result = await stream.sendStream(
        conversationId,
        {
          content: text,
          choice_id: opts?.choice_id,
          choice_set_id: opts?.choice_set_id,
          attachment_ids: opts?.attachment_ids,
          confirm_tool: confirmTool,
          tool_args: opts?.tool_args,
          revise_proposal_id: reviseId,
          owner_mode: opts?.owner_mode,
          reply_language: opts?.reply_language,
        },
        {
          onThinking: () => setThinking(true),
          onStatus: (s) => {
            setThinking(false);
            setStatusRows((prev) => [...prev.filter((p) => p.id !== s.id), s]);
            const hinted = ownerModeFromStreamStatus('chat', s.id);
            if (hinted === 'work') hooksRef.current.onOwnerModeHint?.('work');
          },
          onDelta: (t) => {
            setThinking(false);
            setLiveText((prev) => prev + t);
          },
          onCard: (c) => {
            setCards((prev) => [...prev.filter((x) => x.id !== c.id), c]);
            if (c.kind === 'proposal') {
              const token = c.data?.confirmation_token;
              if (typeof token === 'string' && token.trim()) {
                pendingConfirmRef.current = token.trim();
              }
            }
          },
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
            const nextPending = pendingTokenFromDonePayload(payload);
            if (confirmTool && !nextPending) {
              pendingConfirmRef.current = null;
            } else if (nextPending) {
              pendingConfirmRef.current = nextPending;
            }
            const hinted = ownerModeFromStreamRoute('chat', payload.route);
            if (hinted === 'work') hooksRef.current.onOwnerModeHint?.('work');
            setThinking(false);
            setStatusRows([]);
            const finalText = String(payload.reply_text || '').trim();
            if (finalText) setLiveText(finalText);
            void Promise.resolve(
              hooksRef.current.onTerminal({ expectReplyText: finalText || undefined }),
            ).then((synced) => {
              if (synced !== false) setLiveText('');
            });
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
