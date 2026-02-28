import React from 'react';
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
    if (
      event.reason?.code === 'ERR_NETWORK' || 
      event.reason?.message?.includes('Network Error')
    ) {
      event.preventDefault();
      console.log('Network request failed - backend not available');
    }
  });
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);