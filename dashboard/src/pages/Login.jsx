import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  EnvelopeIcon, 
  LockClosedIcon, 
  SparklesIcon,
  EyeIcon,
  EyeSlashIcon
} from '@heroicons/react/24/outline';
import { useAuth } from '../contexts/AuthContext';
import { errorMessage } from '../utils/apiValidate';

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { login } = /** @type {AuthContextValue} */ (useAuth());
  const location = useLocation();
  const redirectTo = location.state?.from
    ? `${location.state.from.pathname || ''}${location.state.from.search || ''}`
    : '/app';

  /** @param {string} message */
  const isConnectionError = (message) => {
    const value = (message || '').toLowerCase();
    return (
      value.includes('connection timed out') ||
      value.includes('backend running on port 8003') ||
      value.includes('temporarily unavailable') ||
      value.includes('firestore quota') ||
      value.includes('failed to fetch')
    );
  };

  const tryLogin = async () => {
    setLoading(true);
    try {
      await login(email, password, redirectTo);
    } catch (err) {
      setError(errorMessage(err) || 'Login failed. Please try again.');
      console.error('Login error:', err);
    } finally {
      setLoading(false);
    }
  };

  /** @param {import('react').FormEvent<HTMLFormElement>} e */
  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    if (!email || !password) {
      setError('Please enter both email and password.');
      return;
    }
    
    await tryLogin();
  };

  const handleRetryLogin = async () => {
    if (loading) return;
    setError('');

    if (!email || !password) {
      setError('Please enter both email and password.');
      return;
    }

    await tryLogin();
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100 flex items-center justify-center p-4">
      {/* Background Effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-primary-200 rounded-full mix-blend-multiply filter blur-xl opacity-70 animate-pulse-slow"></div>
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-secondary-200 rounded-full mix-blend-multiply filter blur-xl opacity-70 animate-pulse-slow animation-delay-400"></div>
        <div className="absolute top-40 left-1/2 w-80 h-80 bg-accent-200 rounded-full mix-blend-multiply filter blur-xl opacity-70 animate-pulse-slow animation-delay-800"></div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="relative z-10 w-full max-w-md"
      >
        {/* Logo Section */}
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.5 }}
          className="text-center mb-8"
        >
          <div className="inline-flex items-center justify-center w-20 h-20 bg-gradient-to-br from-primary-500 to-secondary-500 rounded-2xl shadow-2xl mb-4">
            <SparklesIcon className="w-10 h-10 text-white" />
          </div>
          <h1 className="text-4xl font-bold gradient-text font-display mb-2">
            Welcome Back
          </h1>
          <p className="text-slate-600">Log in to your Linas AI dashboard</p>
          <p className="mt-2 text-sm text-slate-500">
            <a href="/" className="font-medium text-primary-700 underline">Back to home</a>
            {" · "}
            <a href="/register" className="font-medium text-primary-700 underline">Create Account</a>
          </p>
        </motion.div>

        {/* Login Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="glass rounded-3xl shadow-2xl p-8"
        >
          <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
              <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm" role="alert">
                <p>{error}</p>

                {isConnectionError(error) && (
                  <div className="mt-3 space-y-3 text-xs text-red-700">
                    <p className="font-semibold">Quick checks:</p>
                    <ul className="list-disc pl-5 space-y-1">
                      <li>Start backend and dashboard in separate terminals.</li>
                      <li>Use <strong>http://localhost:3000</strong> for dev mode.</li>
                      <li>If backend only, use <strong>http://localhost:8003</strong>.</li>
                    </ul>

                    <div className="rounded-lg border border-red-200 bg-white/80 p-2 text-[11px] leading-relaxed">
                      <p className="font-semibold">Terminal 1 - backend</p>
                      <code className="block">{'cd "/Users/mahmoudalzougbhi/linas ai bot"'}</code>
                      <code className="block">.venv/bin/python main.py</code>
                      <p className="mt-2 font-semibold">Terminal 2 - dashboard (dev)</p>
                      <code className="block">{'cd "/Users/mahmoudalzougbhi/linas ai bot/dashboard"'}</code>
                      <code className="block">npm start</code>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={handleRetryLogin}
                        disabled={loading}
                        className="px-3 py-1.5 rounded-md bg-red-600 text-white hover:bg-red-700 disabled:opacity-60 disabled:cursor-not-allowed"
                      >
                        Retry Sign In
                      </button>
                      <a
                        href="http://localhost:8003"
                        target="_blank"
                        rel="noreferrer"
                        className="px-3 py-1.5 rounded-md border border-red-300 hover:bg-red-100"
                      >
                        Open Backend
                      </a>
                    </div>
                  </div>
                )}
              </div>
            )}
            {/* Email Field */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Email Address
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <EnvelopeIcon className="h-5 w-5 text-slate-400" />
                </div>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => { setEmail(e.target.value); setError(''); }}
                  className="input-field pl-10 w-full"
                  placeholder="email@example.com"
                  required
                />
              </div>
            </div>

            {/* Password Field */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Password
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <LockClosedIcon className="h-5 w-5 text-slate-400" />
                </div>
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => { setPassword(e.target.value); setError(''); }}
                  className="input-field pl-10 pr-10 w-full"
                  placeholder="Enter your password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center"
                >
                  {showPassword ? (
                    <EyeSlashIcon className="h-5 w-5 text-slate-400 hover:text-slate-600" />
                  ) : (
                    <EyeIcon className="h-5 w-5 text-slate-400 hover:text-slate-600" />
                  )}
                </button>
              </div>
              <div className="mt-2 text-right">
                <a href="/forgot-password" className="text-sm font-medium text-primary-700 underline">
                  Forgot password?
                </a>
              </div>
            </div>

            {/* Submit Button */}
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              type="submit"
              disabled={loading}
              className="w-full btn-primary py-3 text-lg font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <div className="flex items-center justify-center">
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white mr-2"></div>
                  Signing in...
                </div>
              ) : (
                'Sign In'
              )}
            </motion.button>
          </form>

          {/* Divider */}
          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-slate-200"></div>
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-white/80 text-slate-500">Or</span>
            </div>
          </div>

          
        </motion.div>

        {/* Footer */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8 }}
          className="text-center mt-8"
        >
          <p className="text-sm text-slate-500">
            © {new Date().getFullYear()} Linas AI
          </p>
        </motion.div>
      </motion.div>
    </div>
  );
};

export default Login;
