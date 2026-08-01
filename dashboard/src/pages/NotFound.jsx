import React from 'react';
import { Link } from 'react-router-dom';

const NotFound = () => (
  <div className="min-h-[60vh] flex flex-col items-center justify-center text-center px-6">
    <h1 className="text-4xl font-bold text-slate-900 mb-2">Page not found</h1>
    <p className="text-slate-600 mb-6 max-w-md">
      That route does not exist. Use the sidebar to open an available page.
    </p>
    <Link
      to="/"
      className="inline-flex items-center px-4 py-2 rounded-xl bg-primary-600 text-white font-medium hover:bg-primary-700"
    >
      Back to Dashboard
    </Link>
  </div>
);

export default NotFound;
