import React from 'react';
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    // Update state so the next render will show the fallback UI
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    // Log error to console in development
    if (process.env.NODE_ENV === 'development') {
      console.log('Error caught by boundary:', error, errorInfo);
    }
  }

  render() {
    if (this.state.hasError) {
      // Check if it's a network error
      if (this.state.error?.code === 'ERR_NETWORK' || 
          this.state.error?.message?.includes('Network Error')) {
        // Don't show error UI for network errors, just render children
        return this.props.children;
      }

      // Show error UI for other errors
      return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100">
          <div className="text-center p-8">
            <ExclamationTriangleIcon className="w-16 h-16 text-red-500 mx-auto mb-4" />
            <h1 className="text-2xl font-bold text-slate-800 mb-2">Oops! Something went wrong</h1>
            <p className="text-slate-600 mb-4">We encountered an unexpected error.</p>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors"
            >
              Reload Page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;