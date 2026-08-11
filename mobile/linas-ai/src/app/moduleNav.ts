import { useCallback, useState, type Dispatch, type SetStateAction } from 'react';

import { queueNewChat, queueOpenChat } from '../features/chat/pendingChatNav';
import type { ControlArea } from '../features/control/controlAreas';
import type { ModuleNavValue } from '../features/nav/ModuleNavContext';
import type { Screen } from './navigation';

export function activeAreaFromScreen(screen: Screen): ControlArea | 'chat' | null {
  switch (screen.name) {
    case 'chat':
      return 'chat';
    case 'settings':
      return 'settings';
    case 'integrations':
      return 'integrations';
    case 'users':
      return 'users';
    case 'dashboard':
      return 'dashboard';
    case 'billing':
      return 'subscription';
    case 'livechat':
      return 'livechat';
    case 'notifications':
      return 'notifications';
    case 'cm':
    case 'cm_section':
      return 'cm';
    case 'faq':
      return 'faq';
    case 'owner':
      return 'owner';
    default:
      return null;
  }
}

export function useAreaFocusNonce(): [number, () => void] {
  const [areaFocusNonce, setAreaFocusNonce] = useState(0);
  const bump = useCallback(() => setAreaFocusNonce((n) => n + 1), []);
  return [areaFocusNonce, bump];
}

export function buildModuleNavValue(opts: {
  hasAccess: boolean;
  openArea: (area: ControlArea) => void;
  goChat: () => void;
  startNewChat: () => void;
  openChat: (id: string) => void;
  setScreen: Dispatch<SetStateAction<Screen>>;
  areaFocusNonce: number;
  screen: Screen;
}): ModuleNavValue {
  return {
    isAuthenticated: opts.hasAccess,
    openArea: opts.openArea,
    goChat: opts.goChat,
    startNewChat: opts.startNewChat,
    openChat: opts.openChat,
    requestLogin: () => opts.setScreen({ name: 'login' }),
    requestRegister: () => opts.setScreen({ name: 'register' }),
    areaFocusNonce: opts.areaFocusNonce,
    activeArea: activeAreaFromScreen(opts.screen),
  };
}

export function makeChatNavActions(goChat: () => void) {
  return {
    startNewChat: () => {
      queueNewChat();
      goChat();
    },
    openChat: (conversationId: string) => {
      queueOpenChat(conversationId);
      goChat();
    },
  };
}
