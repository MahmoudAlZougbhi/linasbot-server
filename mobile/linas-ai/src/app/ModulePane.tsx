import type { ReactNode } from 'react';

import { EphemeralRoute } from './EphemeralRoute';
import { KeepMountedPane } from './KeepMountedPane';

type Props = {
  keep: boolean;
  active: boolean;
  name: string;
  authEpoch: number;
  children: ReactNode;
};

/**
 * High-use modules stay mounted (hidden). The rest unmount and overlay chat
 * so RAM does not grow with every visited tool.
 */
export function ModulePane({ keep, active, name, authEpoch, children }: Props) {
  if (keep) {
    return (
      <KeepMountedPane key={`${name}-${authEpoch}`} active={active}>
        {children}
      </KeepMountedPane>
    );
  }
  if (!active) return null;
  return <EphemeralRoute>{children}</EphemeralRoute>;
}
