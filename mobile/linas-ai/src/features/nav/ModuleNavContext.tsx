import { createContext, useContext, type ReactNode } from 'react';

import type { ControlArea } from '../control/controlAreas';

export type ModuleNavValue = {
  isAuthenticated: boolean;
  openArea: (area: ControlArea) => void;
  goChat: () => void;
  startNewChat: () => void;
  openChat: (conversationId: string) => void;
  requestLogin: () => void;
  requestRegister: () => void;
  /** Bumps when a module area is opened (incl. re-tap) so keep-mounted screens can reset. */
  areaFocusNonce: number;
  activeArea: ControlArea | 'chat' | null;
};

const ModuleNavContext = createContext<ModuleNavValue | null>(null);

export function ModuleNavProvider({
  value,
  children,
}: {
  value: ModuleNavValue;
  children: ReactNode;
}) {
  return <ModuleNavContext.Provider value={value}>{children}</ModuleNavContext.Provider>;
}

export function useModuleNav(): ModuleNavValue {
  const ctx = useContext(ModuleNavContext);
  if (!ctx) {
    throw new Error('useModuleNav requires ModuleNavProvider');
  }
  return ctx;
}

/** Optional for screens that may render outside the provider (tests / auth). */
export function useModuleNavOptional(): ModuleNavValue | null {
  return useContext(ModuleNavContext);
}
