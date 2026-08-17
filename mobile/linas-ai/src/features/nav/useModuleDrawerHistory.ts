import { useCallback, useEffect, useRef, useState } from 'react';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { ConversationSummarySchema } from '../../api/types';
import { tokenStore } from '../../auth/tokenStore';
import {
  listedHistoryEntries,
  mergeListedHistory,
} from '../chat/chatHistoryVisibility';
import type { HistoryItem } from './HistoryRows';
import { usePinnedChats } from '../chat/usePinnedChats';
import {
  clearDrawerSessionCache,
  getCachedDrawerRecents,
  replaceDrawerRecents,
} from './drawerSessionCache';

const ListConvSchema = z.object({
  success: z.literal(true),
  conversations: z.array(ConversationSummarySchema),
});

/**
 * Lightweight conversation list for module-screen drawers.
 * Seeds from session cache so titles paint before the open-refetch returns.
 */
export function useModuleDrawerHistory(enabled: boolean, drawerOpen: boolean) {
  const cached = getCachedDrawerRecents();
  const [history, setHistory] = useState<HistoryItem[]>(cached.history);
  const [archivedIds, setArchivedIds] = useState<string[]>(cached.archivedIds);
  const [userId, setUserId] = useState<string | null>(null);
  const [workspaceLabel, setWorkspaceLabel] = useState<string | null>(null);
  const { pinnedIds, togglePin } = usePinnedChats(userId);
  const requestIdRef = useRef(0);

  const refresh = useCallback(async () => {
    if (!enabled) {
      setHistory([]);
      setArchivedIds([]);
      return;
    }
    const requestId = ++requestIdRef.current;
    try {
      const listed = await apiFetch('/api/owner-ai/conversations', { schema: ListConvSchema });
      if (requestId !== requestIdRef.current) return;
      const nextHistory = listedHistoryEntries(listed.conversations);
      const nextArchived = listed.conversations.filter((c) => c.archived).map((c) => c.id);
      setHistory((prev) => {
        const merged = mergeListedHistory(prev, nextHistory);
        replaceDrawerRecents(merged, nextArchived);
        return merged;
      });
      setArchivedIds(nextArchived);
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
      clearDrawerSessionCache();
      return;
    }
    const seeded = getCachedDrawerRecents();
    if (seeded.history.length) {
      setHistory(seeded.history);
      setArchivedIds(seeded.archivedIds);
    }
    void tokenStore.getUser().then((u) => {
      setUserId(u?.id ?? null);
      setWorkspaceLabel(u?.tenantId || u?.tenant_id || u?.email || null);
    });
    void refresh();
  }, [enabled, refresh]);

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
