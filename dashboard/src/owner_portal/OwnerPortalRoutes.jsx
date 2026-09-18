import { Navigate, Route } from 'react-router-dom';

import { isMarketingPublicHost } from '../pages/portalHost';
import OwnerPortalShell from './components/OwnerPortalShell';
import OwnerCatalog from './pages/OwnerCatalog';
import OwnerCosts from './pages/OwnerCosts';
import OwnerMessages from './pages/OwnerMessages';
import OwnerOverview from './pages/OwnerOverview';
import OwnerUsers from './pages/OwnerUsers';

function OwnerGate() {
  if (isMarketingPublicHost()) return <Navigate to="/#get-app" replace />;
  return <OwnerPortalShell />;
}

/** Nested `/owner` route tree. URLs stay `/owner` and `/owner/*`. */
export function ownerPortalRouteElements() {
  return (
    <Route path="/owner" element={<OwnerGate />}>
      <Route index element={<OwnerOverview />} />
      <Route path="users" element={<OwnerUsers />} />
      <Route path="messages" element={<OwnerMessages />} />
      <Route path="catalog" element={<OwnerCatalog />} />
      <Route path="costs" element={<OwnerCosts />} />
    </Route>
  );
}
