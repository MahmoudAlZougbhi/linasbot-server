import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { SparklesIcon } from '@heroicons/react/24/outline';
import { PUBLIC_PATHS } from '../constants/publicSite';
import { csrfHeaders } from '../utils/csrf';
import { errorMessage } from '../utils/apiValidate';
import { useAuth } from '../contexts/AuthContext';

const VerifyEmail = () => {
  const [params] = useSearchParams();
  const token = useMemo(() => (params.get('token') || '').trim(), [params]);
  const { refreshUser, user } = /** @type {AuthContextValue} */ (useAuth());
  const [status, setStatus] = useState(/** @type {'idle'|'loading'|'ok'|'error'} */ ('idle'));
  const [message, setMessage] = useState('');
  const [resendLoading, setResendLoading] = useState(false);

  useEffect(() => {
    if (!token) {
      setStatus('idle');
      setMessage('Open the verification link from your email, or resend a new one.');
      return;
    }
    let cancelled = false;
    (async () => {
      setStatus('loading');
      try {
        const response = await fetch('/api/auth/verify-email', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ token }),
        });
        const data = await response.json();
        if (cancelled) return;
        if (!data?.success) {
          throw new Error(data?.error || 'Verification failed');
        }
        setStatus('ok');
        setMessage('Email verified. You can use your full workspace now.');
        try {
          await refreshUser();
        } catch {
          /* ignore */
        }
      } catch (err) {
        if (cancelled) return;
        setStatus('error');
        setMessage(errorMessage(err) || 'Invalid or expired verification link.');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, refreshUser]);

  const resend = async () => {
    setResendLoading(true);
    try {
      const headers = new Headers({ 'Content-Type': 'application/json' });
      const csrf = csrfHeaders();
      Object.entries(csrf).forEach(([key, value]) => {
        if (typeof value === 'string') headers.set(key, value);
      });
      const response = await fetch('/api/auth/resend-verification', {
        method: 'POST',
        headers,
        credentials: 'include',
        body: JSON.stringify({ email: user?.email || undefined }),
      });
      const data = await response.json();
      setMessage(typeof data?.message === 'string' ? data.message : 'If needed, a new email was sent.');
    } catch (err) {
      setMessage(errorMessage(err) || 'Could not resend verification email.');
    } finally {
      setResendLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-sky-50 to-fuchsia-50 flex items-center justify-center p-4">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-md glass rounded-3xl p-8 shadow-2xl">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-4 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-primary-500 to-secondary-500">
            <SparklesIcon className="h-7 w-7 text-white" />
          </div>
          <h1 className="font-display text-3xl font-bold text-slate-950">Verify email</h1>
        </div>
        <p className="text-sm text-slate-700" role="status">
          {status === 'loading' ? 'Verifying…' : message}
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={resend}
            disabled={resendLoading}
            className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 disabled:opacity-50"
          >
            {resendLoading ? 'Sending…' : 'Resend email'}
          </button>
          <Link to={PUBLIC_PATHS.appHome} className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white">
            Go to dashboard
          </Link>
          <Link to={PUBLIC_PATHS.login} className="rounded-xl px-4 py-2 text-sm font-semibold text-primary-700 underline">
            Sign in
          </Link>
        </div>
      </motion.div>
    </div>
  );
};

export default VerifyEmail;
