import { StrictMode } from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import ErrorBoundary from './components/Common/ErrorBoundary';

// Suppress network errors in development
if (process.env.NODE_ENV === 'development') {
  const originalError = console.error;
  console.error = (...args) => {
    if (
      typeof args[0] === 'string' && 
      (args[0].includes('Network Error') || 
       args[0].includes('ERR_NETWORK') ||
       args[0].includes('Failed to fetch'))
    ) {
      // Suppress network error logs
      console.log('Backend server is not running. Dashboard will work with mock data.');
      return;
    }
    originalError.apply(console, args);
  };

  // Handle unhandled promise rejections
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;
    const code =
      typeof reason === 'object' && reason && 'code' in reason
        ? String(/** @type {{ code?: unknown }} */ (reason).code)
        : '';
    const message =
      reason instanceof Error
        ? reason.message
        : typeof reason === 'object' && reason && 'message' in reason
          ? String(/** @type {{ message?: unknown }} */ (reason).message)
          : '';
    if (code === 'ERR_NETWORK' || message.includes('Network Error')) {
      event.preventDefault();
      console.log('Network request failed - backend not available');
    }
  });
}

const rootEl = document.getElementById('root');
if (!rootEl) {
  throw new Error('Root element #root not found');
}
const root = ReactDOM.createRoot(rootEl);
root.render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>
);