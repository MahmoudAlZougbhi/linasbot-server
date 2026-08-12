import { Component } from 'react';
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';

/**
 * @typedef {object} ErrorBoundaryProps
 * @property {import('react').ReactNode} children
 */

/**
 * @typedef {object} ErrorBoundaryState
 * @property {boolean} hasError
 * @property {Error | null} error
 */

/** @extends {Component<ErrorBoundaryProps, ErrorBoundaryState>} */
class ErrorBoundary extends Component {
  /** @param {ErrorBoundaryProps} props */
  constructor(props) {
    super(props);
    /** @type {ErrorBoundaryState} */
    this.state = { hasError: false, error: null };
  }

  /**
   * @param {Error} error
   * @returns {ErrorBoundaryState}
   */
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  /**
   * @param {Error} error
   * @param {import('react').ErrorInfo} errorInfo
   */
  componentDidCatch(error, errorInfo) {
    if (process.env.NODE_ENV === 'development') {
      console.log('Error caught by boundary:', error, errorInfo);
    }
  }

  render() {
    if (this.state.hasError) {
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
