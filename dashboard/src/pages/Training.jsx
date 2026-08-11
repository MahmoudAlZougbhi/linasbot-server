import { Navigate } from "react-router-dom";

/**
 * Legacy FAQ / Bot Training URL.
 * Canonical FAQ authoring lives only under AI Setup → FAQ.
 * Keep this route as a clear redirect so bookmarks and old links still work.
 */
const Training = () => {
  return <Navigate to="/content-managers/faq" replace />;
};

export default Training;
