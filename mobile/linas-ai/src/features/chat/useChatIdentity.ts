import { useEffect, useState } from 'react';

import { tokenStore } from '../../auth/tokenStore';
import { clearPendingGuestDraft, loadPendingGuestDraft } from './pendingGuestDraft';

/** Loads owner workspace label + restores guest draft after login. */
export function useChatIdentity(isAuthenticated: boolean, setDraft: (text: string) => void) {
  const [userId, setUserId] = useState<string | null>(null);
  const [workspaceLabel, setWorkspaceLabel] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated) {
      setUserId(null);
      setWorkspaceLabel(null);
      return;
    }
    void tokenStore.getUser().then((u) => {
      setUserId(u?.id ?? null);
      setWorkspaceLabel(u?.tenantId || u?.tenant_id || u?.email || null);
    });
    void loadPendingGuestDraft().then((pending) => {
      if (pending?.text) {
        setDraft(pending.text);
        void clearPendingGuestDraft();
      }
    });
  }, [isAuthenticated, setDraft]);

  return { userId, workspaceLabel };
}
