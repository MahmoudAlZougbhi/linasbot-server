# BLOCKED: dashboard/src/pages/Analytics.jsx

**Status:** BLOCKED — not deleted  
**Date:** 2026-08-12  
**Branch:** chore/project-cleanup-reorg

## Candidate

`dashboard/src/pages/Analytics.jsx` (and its unit test `Analytics.test.jsx`) were considered for deletion because `/analytics` is product-disabled and `App.jsx` redirects `/analytics` → `/app`.

## Blocker evidence

`/app` is the live dashboard home route and **renders Analytics via Dashboard**:

```1:5:dashboard/src/pages/Dashboard.jsx
import Analytics from './Analytics';

const Dashboard = () => {
  return <Analytics />;
};
```

```113:113:dashboard/src/App.jsx
                    <Route path="/app" element={<Dashboard />} />
```

| Check | Result |
|---|---|
| `App.jsx` `/analytics` | Redirect only (`Navigate to="/app"`) — page component not mounted on that path |
| `App.jsx` `/app` | Mounts lazy `Dashboard` |
| `Dashboard.jsx` | Directly imports and returns `<Analytics />` |
| `Analytics.test.jsx` | Active unit coverage for the home analytics UI |

## Action

**Skip deletion.** Removing `Analytics.jsx` would break `/app` home. Redirect for `/analytics` and `DISABLED_FRONTEND_ROUTES` entry may remain; they only hide the standalone URL, not the home composition.
