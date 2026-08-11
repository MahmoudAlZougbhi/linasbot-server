import { useCallback, useEffect, useState } from 'react';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { ConversationSummarySchema } from '../../api/types';
import { tokenStore } from '../../auth/tokenStore';
import type { HistoryItem } from './HistoryRows';
import { usePinnedChats } from '../chat/usePinnedChats';

const ListConvSchema = z.object({
  success: z.literal(true),
  conversations: z.array(ConversationSummarySchema),
});

/**
 * Lightweight conversation list for module-screen drawers.
 * Does not bootstrap an active chat session (ChatScreen owns that).
 */
export function useModuleDrawerHistory(enabled: boolean, drawerOpen: boolean) {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [archivedIds, setArchivedIds] = useState<string[]>([]);
  const [userId, setUserId] = useState<string | null>(null);
  const [workspaceLabel, setWorkspaceLabel] = useState<string | null>(null);
  const { pinnedIds, togglePin } = usePinnedChats(userId);

  const refresh = useCallback(async () => {
    if (!enabled) {
      setHistory([]);
      setArchivedIds([]);
      return;
    }
    try {
      const listed = await apiFetch('/api/owner-ai/conversations', { schema: ListConvSchema });
      setHistory(listed.conversations.map((c) => ({ id: c.id, title: c.title })));
      setArchivedIds(listed.conversations.filter((c) => c.archived).map((c) => c.id));
    } catch {
      /* keep last good list */
    }
  }, [enabled]);

  useEffect(() => {
    if (!enabled) {
      setUserId(null);
      setWorkspaceLabel(null);
      setHistory([]);
      setArchivedIds([]);
      return;
    }
    void tokenStore.getUser().then((u) => {
      setUserId(u?.id ?? null);
      setWorkspaceLabel(u?.tenantId || u?.tenant_id || u?.email || null);
    });
  }, [enabled]);

  useEffect(() => {
    if (enabled && drawerOpen) {
      void refresh();
    }
  }, [enabled, drawerOpen, refresh]);

  const rename = useCallback(async (id: string, title: string) => {
    await apiFetch(`/api/owner-ai/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
      schema: z.object({ success: z.literal(true) }),
    });
    setHistory((prev) => prev.map((h) => (h.id === id ? { ...h, title } : h)));
  }, []);

  const setArchived = useCallback(async (id: string, archived: boolean) => {
    await apiFetch(`/api/owner-ai/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ archived }),
      schema: z.object({ success: z.literal(true) }),
    });
    setArchivedIds((prev) =>
      archived ? (prev.includes(id) ? prev : [...prev, id]) : prev.filter((x) => x !== id),
    );
  }, []);

  const remove = useCallback(async (id: string) => {
    await apiFetch(`/api/owner-ai/conversations/${id}`, {
      method: 'DELETE',
      schema: z.object({ success: z.literal(true) }),
    });
    setHistory((prev) => prev.filter((h) => h.id !== id));
    setArchivedIds((prev) => prev.filter((x) => x !== id));
  }, []);

  return {
    history,
    archivedIds,
    pinnedIds,
    workspaceLabel,
    togglePin,
    rename,
    setArchived,
    remove,
  };
}
