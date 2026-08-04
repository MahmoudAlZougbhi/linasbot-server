import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { LockClosedIcon, SparklesIcon } from '@heroicons/react/24/outline';
import { PUBLIC_PATHS } from '../constants/publicSite';
import { errorMessage } from '../utils/apiValidate';

const ResetPassword = () => {
  const [params] = useSearchParams();
  const token = useMemo(() => (params.get('token') || '').trim(), [params]);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');

  /** @param {import('react').FormEvent<HTMLFormElement>} e */
  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!token) {
      setError('This reset link is missing a token.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setLoading(true);
    try {
      const response = await fetch('/api/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ token, new_password: password }),
      });
      const data = await response.json();
      if (!data?.success) {
        throw new Error(data?.error || 'Reset failed');
      }
      setDone(true);
    } catch (err) {
      setError(errorMessage(err) || 'Could not reset password.');
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
          <h1 className="text-3xl font-bold gradient-text font-display">Choose a new password</h1>
        </div>
        <div className="glass rounded-3xl shadow-2xl p-8">
          {done ? (
            <div className="space-y-4 text-sm text-slate-700" role="status">
              <p>Password updated. You can sign in now.</p>
              <Link to={PUBLIC_PATHS.login} className="font-semibold text-primary-700 underline">
                Sign in
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              {error && (
                <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">
                  {error}
                </div>
              )}
              {!token && (
                <p className="text-sm text-amber-700">Open the link from your email to continue.</p>
              )}
              <div>
                <label htmlFor="new-password" className="mb-2 block text-sm font-medium text-slate-700">
                  New password
                </label>
                <div className="relative">
                  <LockClosedIcon className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
                  <input
                    id="new-password"
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="input-field w-full pl-10"
                    autoComplete="new-password"
                  />
                </div>
              </div>
              <div>
                <label htmlFor="confirm-password" className="mb-2 block text-sm font-medium text-slate-700">
                  Confirm password
                </label>
                <input
                  id="confirm-password"
                  type="password"
                  required
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  className="input-field w-full"
                  autoComplete="new-password"
                />
              </div>
              <button
                type="submit"
                disabled={loading || !token}
                className="w-full btn-primary py-3 font-semibold disabled:opacity-50"
              >
                {loading ? 'Saving…' : 'Update password'}
              </button>
            </form>
          )}
        </div>
      </motion.div>
    </div>
  );
};

export default ResetPassword;
