const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  // Proxy for backend API endpoints (agent routes)
  app.use(
    '/agent',
    createProxyMiddleware({
      target: 'https://boc-lb.com',
      changeOrigin: true,
      secure: false,
      logLevel: 'debug',
      onProxyReq: (proxyReq, req, res) => {
        console.log(`[Proxy] ${req.method} ${req.url} -> https://boc-lb.com${req.url}`);
      },
      onProxyRes: (proxyRes, req, res) => {
        console.log(`[Proxy] Response: ${proxyRes.statusCode} for ${req.url}`);
      },
      onError: (err, req, res) => {
        console.error('[Proxy] Error:', err.message);
      }
    })
  );

  // Proxy for local backend (if needed)
  app.use(
    '/api',
    createProxyMiddleware({
      target: 'http://localhost:8003',
      changeOrigin: true,
      logLevel: 'debug'
    })
  );
};
