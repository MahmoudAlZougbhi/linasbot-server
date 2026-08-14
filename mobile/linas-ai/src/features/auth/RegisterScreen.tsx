import { useState } from 'react';

import { ApiError, mobileLogin } from '../../api/client';
import { useI18n } from '../../i18n/LanguageContext';
import {
  patchOwnerGender,
  registerAccount,
  resendVerification,
  verifyEmailCode,
} from './authRemote';
import { businessNameFromEmail } from './businessNameFromEmail';
import { SignupAddressStep, type AddressGender } from './SignupAddressStep';
import { SignupCredentialsStep } from './SignupCredentialsStep';
import { SignupSuccessStep } from './SignupSuccessStep';
import { SignupVerifyStep } from './SignupVerifyStep';

type Step = 'credentials' | 'verify' | 'address' | 'success';

type Props = {
  onBack: () => void;
  onLoggedIn?: () => void;
};

export function RegisterScreen({ onBack, onLoggedIn }: Props) {
  const { tr, language } = useI18n();
  const [step, setStep] = useState<Step>('credentials');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [code, setCode] = useState('');
  const [gender, setGender] = useState<AddressGender>('unset');
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function socialDone() {
    onLoggedIn?.();
  }

  async function onContinueCredentials() {
    const mail = email.trim();
    if (!mail || !mail.includes('@') || password.length < 12) {
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
      const result = await registerAccount({
        email: mail,
        password,
        businessName: businessNameFromEmail(mail),
        gender: 'unset',
        preferredLanguage: language,
      });
      if (result.success) {
        setCode('');
        setStep('verify');
        return;
      }
      setMessage(result.error ?? tr('registerFailed'));
    } catch (err) {
      setMessage(err instanceof ApiError ? tr('registerFailed') : tr('networkError'));
    } finally {
      setLoading(false);
    }
  }

  async function onVerify() {
    if (code.replace(/\D/g, '').length !== 6) {
      setMessage(tr('codeIncomplete'));
      return;
    }
    setLoading(true);
    setMessage(null);
    try {
      const result = await verifyEmailCode(email.trim(), code.replace(/\D/g, ''));
      if (result.success) {
        setStep('address');
        return;
      }
      setMessage(result.error ?? tr('invalidOrExpiredCode'));
    } catch {
      setMessage(tr('verifyEmailFailed'));
    } finally {
      setLoading(false);
    }
  }

  async function onResend() {
    setMessage(null);
    try {
      const result = await resendVerification(email.trim());
      if (!result.success) setMessage(result.error ?? tr('resendFailed'));
    } catch {
      setMessage(tr('resendFailed'));
    }
  }

  async function onFinish() {
    setLoading(true);
    setMessage(null);
    try {
      await mobileLogin(email.trim(), password);
      await patchOwnerGender(gender);
      setStep('success');
    } catch (err) {
      setMessage(err instanceof ApiError ? tr('loginGenericError') : tr('networkError'));
    } finally {
      setLoading(false);
    }
  }

  if (step === 'verify') {
    return (
      <SignupVerifyStep
        email={email}
        code={code}
        message={message}
        loading={loading}
        onCode={setCode}
        onVerify={() => void onVerify()}
        onResend={() => void onResend()}
        onChangeEmail={() => {
          setMessage(null);
          setStep('credentials');
        }}
        onBack={() => {
          setMessage(null);
          setStep('credentials');
        }}
      />
    );
  }
  if (step === 'address') {
    return (
      <SignupAddressStep
        gender={gender}
        message={message}
        loading={loading}
        onGender={setGender}
        onFinish={() => void onFinish()}
        onBack={() => {
          setMessage(null);
          setStep('verify');
        }}
      />
    );
  }
  if (step === 'success') {
    return <SignupSuccessStep onContinue={() => onLoggedIn?.()} />;
  }
  return (
    <SignupCredentialsStep
      email={email}
      password={password}
      confirm={confirm}
      message={message}
      loading={loading}
      onEmail={setEmail}
      onPassword={setPassword}
      onConfirm={setConfirm}
      onContinue={() => void onContinueCredentials()}
      onBack={onBack}
      onGoLogin={onBack}
      onSocialSuccess={socialDone}
      onSocialError={setMessage}
    />
  );
}
