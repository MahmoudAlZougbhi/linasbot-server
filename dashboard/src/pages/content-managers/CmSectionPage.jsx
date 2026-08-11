import { Link, Navigate, useParams } from "react-router-dom";
import { findCmSectionBySlug } from "./cmSections";

/**
 * Fallback route — normal owner workflow uses dedicated form pages.
 * Never renders a raw JSON editor.
 */
const CmSectionPage = () => {
  const { sectionSlug = "" } = useParams();
  const card = findCmSectionBySlug(sectionSlug);

  if (!card) {
    return <Navigate to="/content-managers" replace />;
  }

  // Dedicated form routes are registered explicitly in App.jsx; this fallback
  // only catches unknown future slugs without exposing JSON.
  if (card.section === null) {
    if (card.slug === "sources") return <Navigate to="/content-managers/sources" replace />;
    return <Navigate to="/content-managers/publish" replace />;
  }

  return (
    <div className="space-y-4 max-w-xl">
      <h1 className="text-2xl font-semibold text-slate-900">{card.name}</h1>
      <p className="text-slate-600">
        This section uses a guided form. If you reached this page unexpectedly, open it from the AI Setup hub.
      </p>
      <Link to={`/content-managers/${card.slug}`} className="text-emerald-700 hover:underline">
        Open {card.name}
      </Link>
      <div>
        <Link to="/content-managers" className="text-sm text-slate-500 hover:underline">
          ← Back to AI Setup
        </Link>
      </div>
    </div>
  );
};

export default CmSectionPage;
