import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'linas_pending_guest_draft_v1';

export type PendingGuestDraft = {
  text: string;
  createdAt: number;
  guestSessionId?: string;
};

/** UX-only pending draft handoff — never imports guest transcript into owner memory. */
export async function savePendingGuestDraft(draft: PendingGuestDraft): Promise<void> {
  const text = draft.text.trim();
  if (!text) {
    await AsyncStorage.removeItem(KEY);
    return;
  }
  await AsyncStorage.setItem(KEY, JSON.stringify({ ...draft, text }));
}

export async function loadPendingGuestDraft(): Promise<PendingGuestDraft | null> {
  const raw = await AsyncStorage.getItem(KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as PendingGuestDraft;
    if (!parsed?.text?.trim()) return null;
    return parsed;
  } catch {
    return null;
  }
}

export async function clearPendingGuestDraft(): Promise<void> {
  await AsyncStorage.removeItem(KEY);
}
