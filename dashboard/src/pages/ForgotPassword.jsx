import { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { EnvelopeIcon, SparklesIcon } from '@heroicons/react/24/outline';
import { PUBLIC_PATHS } from '../constants/publicSite';
import { errorMessage } from '../utils/apiValidate';

const ForgotPassword = () => {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  /** @param {import('react').FormEvent<HTMLFormElement>} e */
  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const response = await fetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email: email.trim() }),
      });
      const data = await response.json();
      if (!data?.success) {
        throw new Error(data?.error || 'Request failed');
      }
      setDone(true);
      setMessage(typeof data.message === 'string' ? data.message : 'Check your email for a reset link.');
    } catch (err) {
      setError(errorMessage(err) || 'Could not start password reset.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br from-primary-500 to-secondary-500 rounded-2xl shadow-xl mb-4">
            <SparklesIcon className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-3xl font-bold gradient-text font-display">Forgot password</h1>
          <p className="mt-2 text-slate-600">We will email you a secure reset link.</p>
        </div>
        <div className="glass rounded-3xl shadow-2xl p-8">
          {done ? (
            <div className="space-y-4 text-sm text-slate-700" role="status">
              <p>{message}</p>
              <Link to={PUBLIC_PATHS.login} className="font-semibold text-primary-700 underline">
                Back to sign in
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              {error && (
                <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">
                  {error}
                </div>
              )}
              <div>
                <label htmlFor="forgot-email" className="mb-2 block text-sm font-medium text-slate-700">
                  Email
                </label>
                <div className="relative">
                  <EnvelopeIcon className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
                  <input
                    id="forgot-email"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="input-field w-full pl-10"
                    placeholder="email@example.com"
                    autoComplete="email"
                  />
                </div>
              </div>
              <button type="submit" disabled={loading} className="w-full btn-primary py-3 font-semibold disabled:opacity-50">
                {loading ? 'Sending…' : 'Send reset link'}
              </button>
              <p className="text-center text-sm text-slate-500">
                <Link to={PUBLIC_PATHS.login} className="font-medium text-primary-700 underline">
                  Back to sign in
                </Link>
              </p>
            </form>
          )}
        </div>
      </motion.div>
    </div>
  );
};

export default ForgotPassword;
