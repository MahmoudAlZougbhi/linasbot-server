import { useEffect, useState } from 'react';

import { tokenStore } from '../../auth/tokenStore';
import { allowedAccessChannels, type AccessChannelId } from '../users/usersAccess';
import { resolvePermissions } from '../users/usersPermissions';

export function useLiveChatAccess() {
  const [canChats, setCanChats] = useState(true);
  const [canComments, setCanComments] = useState(true);
  const [allowedChannels, setAllowedChannels] = useState<AccessChannelId[] | null>(null);

  useEffect(() => {
    void tokenStore.getUser().then((user) => {
      if (!user) return;
      const perms = resolvePermissions(user.role, user.permissions ?? null);
      setCanChats(perms.liveChat === true);
      setCanComments(perms.comments === true);
      setAllowedChannels(allowedAccessChannels(perms));
    });
  }, []);

  return { canChats, canComments, allowedChannels };
}
