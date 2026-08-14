import { useEffect, useRef, useState } from 'react';

import { useModuleNav } from '../nav/ModuleNavContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import { useI18n } from '../../i18n/LanguageContext';
import { useTheme } from '../../theme';
import { RequestDetailView } from './RequestDetailView';
import { RequestsHome } from './RequestsHome';
import { useRequestsList } from './useRequestsList';
import type { RequestCard } from './requestsTypes';

type LiveChatTarget = { userId: string; conversationId: string };

type Props = {
  onOpenLiveChat: (target: LiveChatTarget) => void;
};

/**
 * Operator Requests module — list + detail against `/api/requests*`.
 * Re-tapping Requests in the drawer returns to the list (keep-mounted safe).
 */
export function RequestsScreen({ onOpenLiveChat }: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();
  const nav = useModuleNav();
  const active = nav.activeArea === 'requests';
  const list = useRequestsList(nav.isAuthenticated && active);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const focusNonceSeen = useRef(nav.areaFocusNonce);

  useEffect(() => {
    if (!active) return;
    if (focusNonceSeen.current === nav.areaFocusNonce) return;
    focusNonceSeen.current = nav.areaFocusNonce;
    setSelectedId(null);
    void list.refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refresh identity is stable enough
  }, [nav.areaFocusNonce, active]);

  if (selectedId) {
    return (
      <ScreenChrome
        title={tr('reqDetailTitle')}
        subtitle={tr('reqSubtitle')}
        titleColor={colors.accent}
        iconColor={colors.accent}
      >
        <RequestDetailView
          requestId={selectedId}
          user={list.user}
          onBack={() => {
            setSelectedId(null);
            void list.refresh();
          }}
          onOpenLiveChat={onOpenLiveChat}
        />
      </ScreenChrome>
    );
  }

  return (
    <ScreenChrome
      title={tr('reqTitle')}
      subtitle={tr('reqSubtitle')}
      titleColor={colors.accent}
      iconColor={colors.accent}
    >
      <RequestsHome
        list={list}
        onOpen={(item: RequestCard) => setSelectedId(item.request_id)}
        onOpenAiSetup={() => nav.openArea('cm')}
        onOpenLiveChat={onOpenLiveChat}
      />
    </ScreenChrome>
  );
}
