import { useState } from 'react';

import { ApiError } from '../../api/client';
import { useI18n } from '../../i18n/LanguageContext';
import { requestPasswordReset, resetPasswordWithCode } from './authRemote';
import { ForgotCodeStep } from './ForgotCodeStep';
import { ForgotEmailStep } from './ForgotEmailStep';
import { ForgotNewPasswordStep } from './ForgotNewPasswordStep';

type Step = 'email' | 'code' | 'password';

type Props = {
  onBack: () => void;
  onDone: () => void;
};

export function ForgotPasswordScreen({ onBack, onDone }: Props) {
  const { tr } = useI18n();
  const [step, setStep] = useState<Step>('email');
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSend() {
    const mail = email.trim();
    if (!mail || !mail.includes('@')) {
      setMessage(tr('emailRequired'));
      return;
    }
    setLoading(true);
    setMessage(null);
    try {
      await requestPasswordReset(mail);
      setCode('');
      setStep('code');
    } catch {
      setMessage(tr('networkError'));
    } finally {
      setLoading(false);
    }
  }

  async function onResend() {
    setMessage(null);
    try {
      await requestPasswordReset(email.trim());
    } catch {
      setMessage(tr('resendFailed'));
    }
  }

  function onContinueCode() {
    if (code.replace(/\D/g, '').length !== 6) {
      setMessage(tr('codeIncomplete'));
      return;
    }
    setMessage(null);
    setStep('password');
  }

  async function onReset() {
    if (password.length < 12) {
      setMessage(tr('registerNeedCredentials'));
      return;
    }
    if (password !== confirm) {
      setMessage(tr('passwordsDoNotMatch'));
      return;
    }
    setLoading(true);
    setMessage(null);
    try {
      const result = await resetPasswordWithCode(email.trim(), code.replace(/\D/g, ''), password);
      if (result.success) {
        onDone();
        return;
      }
      setMessage(result.error ?? tr('invalidOrExpiredCode'));
    } catch (err) {
      setMessage(err instanceof ApiError ? tr('resetPasswordFailed') : tr('networkError'));
    } finally {
      setLoading(false);
    }
  }

  if (step === 'code') {
    return (
      <ForgotCodeStep
        email={email}
        code={code}
        message={message}
        loading={loading}
        onCode={setCode}
        onContinue={onContinueCode}
        onResend={() => void onResend()}
        onChangeEmail={() => {
          setMessage(null);
          setStep('email');
        }}
        onBack={() => {
          setMessage(null);
          setStep('email');
        }}
      />
    );
  }
  if (step === 'password') {
    return (
      <ForgotNewPasswordStep
        password={password}
        confirm={confirm}
        message={message}
        loading={loading}
        onPassword={setPassword}
        onConfirm={setConfirm}
        onReset={() => void onReset()}
        onBack={() => {
          setMessage(null);
          setStep('code');
        }}
      />
    );
  }
  return (
    <ForgotEmailStep
      email={email}
      message={message}
      loading={loading}
      onEmail={setEmail}
      onSend={() => void onSend()}
      onBack={onBack}
    />
  );
}
