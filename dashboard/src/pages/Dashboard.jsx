import { Link } from 'react-router-dom';
import { SAAS_NAV_ITEMS } from '../constants/productFeatures';

/**
 * Operator /app home — replaces the disabled Analytics dashboard surface.
 * Deep links to enabled SaaS areas; public marketing stays on landing routes.
 */
const Dashboard = () => {
  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Linas AI</h1>
        <p className="mt-2 text-sm text-gray-600">
          Operator home. Prefer the Linas AI mobile app for day-to-day work; use the links below when you need the web tools that are still enabled.
        </p>
      </div>
      <ul className="grid gap-3 sm:grid-cols-2">
        {SAAS_NAV_ITEMS.filter((item) => item.href !== '/app').map((item) => (
          <li key={item.href}>
            <Link
              to={item.href}
              className="block rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-gray-900 hover:border-gray-400"
            >
              {item.name}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default Dashboard;
