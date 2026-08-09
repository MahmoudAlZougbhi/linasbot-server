import AsyncStorage from '@react-native-async-storage/async-storage';
import { useCallback, useEffect, useState } from 'react';

function keyFor(userId: string): string {
  return `linas_pinned_chats_${userId || 'anon'}`;
}

export function usePinnedChats(userId: string | null) {
  const [pinnedIds, setPinnedIds] = useState<string[]>([]);

  useEffect(() => {
    if (!userId) {
      setPinnedIds([]);
      return;
    }
    void (async () => {
      const raw = await AsyncStorage.getItem(keyFor(userId));
      if (!raw) {
        setPinnedIds([]);
        return;
      }
      try {
        const parsed: unknown = JSON.parse(raw);
        if (Array.isArray(parsed) && parsed.every((x) => typeof x === 'string')) {
          setPinnedIds(parsed);
        }
      } catch {
        setPinnedIds([]);
      }
    })();
  }, [userId]);

  const persist = useCallback(
    async (next: string[]) => {
      setPinnedIds(next);
      if (!userId) {
        return;
      }
      await AsyncStorage.setItem(keyFor(userId), JSON.stringify(next));
    },
    [userId],
  );

  const togglePin = useCallback(
    async (conversationId: string) => {
      const next = pinnedIds.includes(conversationId)
        ? pinnedIds.filter((id) => id !== conversationId)
        : [conversationId, ...pinnedIds];
      await persist(next);
    },
    [persist, pinnedIds],
  );

  const isPinned = useCallback((id: string) => pinnedIds.includes(id), [pinnedIds]);

  return { pinnedIds, togglePin, isPinned };
}
