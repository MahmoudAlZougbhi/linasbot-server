import React, { useState } from 'react';

// Simple API test page with visible debug info
const SimpleApiTest = () => {
  const [debugInfo, setDebugInfo] = useState([]);
  const [testing, setTesting] = useState(false);

  const addDebug = (message, type = 'info') => {
    const timestamp = new Date().toLocaleTimeString();
    setDebugInfo(prev => [...prev, { message, type, timestamp }]);
  };

  const testHealthEndpoint = async () => {
    setTesting(true);
    setDebugInfo([]);
    
    addDebug('🚀 Starting test...', 'info');
    addDebug(`📍 Testing URL: /agent/health`, 'info');
    addDebug(`🏠 Current origin: ${window.location.origin}`, 'info');
    
    try {
      const url = '/agent/health';
      addDebug(`🌐 Full URL: ${window.location.origin}${url}`, 'info');
      addDebug('📤 Sending fetch request...', 'info');
      
      const startTime = Date.now();
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        }
      });
      
      const responseTime = Date.now() - startTime;
      addDebug(`⏱️ Response time: ${responseTime}ms`, 'info');
      addDebug(`📊 Status: ${response.status} ${response.statusText}`, response.ok ? 'success' : 'error');
      addDebug(`📋 Content-Type: ${response.headers.get('content-type')}`, 'info');
      
      const text = await response.text();
      addDebug(`📄 Response length: ${text.length} characters`, 'info');
      addDebug(`📄 Response preview: ${text.substring(0, 200)}...`, 'info');
      
      try {
        const json = JSON.parse(text);
        addDebug('✅ Response is valid JSON', 'success');
        addDebug(`📦 JSON data: ${JSON.stringify(json, null, 2)}`, 'success');
      } catch (e) {
        addDebug('❌ Response is NOT JSON', 'error');
        addDebug(`🔍 Parse error: ${e.message}`, 'error');
        
        if (text.includes('<!DOCTYPE') || text.includes('<html')) {
          addDebug('🌐 Response is HTML (endpoint might not exist)', 'error');
        }
      }
      
    } catch (error) {
      addDebug(`💥 Fetch failed: ${error.message}`, 'error');
      addDebug(`📛 Error type: ${error.name}`, 'error');
      
      if (error.message.includes('Failed to fetch')) {
        addDebug('🚫 This is likely a CORS or network error', 'error');
        addDebug('💡 Possible causes:', 'error');
        addDebug('   1. Proxy not configured', 'error');
        addDebug('   2. Backend not running', 'error');
        addDebug('   3. Network issue', 'error');
      }
    }
    
    setTesting(false);
    addDebug('🏁 Test completed', 'info');
  };

  const testWithFullURL = async () => {
    setTesting(true);
    setDebugInfo([]);
    
    addDebug('🚀 Testing with full URL (bypassing proxy)...', 'info');
    
    try {
      const url = 'https://boc-lb.com/agent/health';
      addDebug(`🌐 Full URL: ${url}`, 'info');
      addDebug('📤 Sending fetch request...', 'info');
      
      const startTime = Date.now();
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        }
      });
      
      const responseTime = Date.now() - startTime;
      addDebug(`⏱️ Response time: ${responseTime}ms`, 'info');
      addDebug(`📊 Status: ${response.status}`, response.ok ? 'success' : 'error');
      
      const text = await response.text();
      addDebug(`📄 Response: ${text.substring(0, 200)}`, 'info');
      
    } catch (error) {
      addDebug(`💥 Fetch failed: ${error.message}`, 'error');
      
      if (error.message.includes('Failed to fetch')) {
        addDebug('🚫 CORS Error - This is expected!', 'error');
        addDebug('✅ This means the API exists but blocks browser requests', 'success');
        addDebug('💡 The proxy should fix this', 'info');
      }
    }
    
    setTesting(false);
    addDebug('🏁 Test completed', 'info');
  };

  const clearDebug = () => {
    setDebugInfo([]);
  };

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold mb-6">Simple API Test</h1>
      
      <div className="space-y-4 mb-6">
        <button
          onClick={testHealthEndpoint}
          disabled={testing}
          className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {testing ? 'Testing...' : 'Test /agent/health (with proxy)'}
        </button>
        
        <button
          onClick={testWithFullURL}
          disabled={testing}
          className="px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed ml-4"
        >
          {testing ? 'Testing...' : 'Test Full URL (no proxy)'}
        </button>
        
        <button
          onClick={clearDebug}
          className="px-6 py-3 bg-gray-600 text-white rounded-lg hover:bg-gray-700 ml-4"
        >
          Clear
        </button>
      </div>

      <div className="bg-gray-900 text-gray-100 p-6 rounded-lg font-mono text-sm overflow-auto max-h-96">
        {debugInfo.length === 0 ? (
          <p className="text-gray-400">Click a button to start testing...</p>
        ) : (
          debugInfo.map((item, index) => (
            <div
              key={index}
              className={`mb-2 ${
                item.type === 'error' ? 'text-red-400' :
                item.type === 'success' ? 'text-green-400' :
                'text-gray-300'
              }`}
            >
              <span className="text-gray-500">[{item.timestamp}]</span> {item.message}
            </div>
          ))
        )}
      </div>

      <div className="mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
        <h3 className="font-bold text-yellow-800 mb-2">📝 Instructions:</h3>
        <ol className="list-decimal list-inside space-y-1 text-sm text-yellow-700">
          <li>Click "Test /agent/health (with proxy)" button</li>
          <li>Watch the debug output above</li>
          <li>Also open DevTools (F12) → Network tab</li>
          <li>Look for the request to /agent/health</li>
          <li>Check what URL it actually calls and what response it gets</li>
        </ol>
      </div>

      <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
        <h3 className="font-bold text-blue-800 mb-2">🔍 What to Look For:</h3>
        <ul className="list-disc list-inside space-y-1 text-sm text-blue-700">
          <li><strong>If proxy works:</strong> You'll see JSON response or 401/404 error</li>
          <li><strong>If proxy doesn't work:</strong> You'll see HTML or "Failed to fetch"</li>
          <li><strong>If CORS error:</strong> The full URL test will fail, but proxy test should work</li>
        </ul>
      </div>
    </div>
  );
};

export default SimpleApiTest;
