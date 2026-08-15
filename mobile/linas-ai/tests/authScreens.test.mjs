/**
 * Auth handoff: login / create-account / forgot-password screens + API wiring.
 * Run: node --test mobile/linas-ai/tests/authScreens.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

describe('login Welcome back screen', () => {
  it('matches sparkle + copy + forgot + circular social + guest', () => {
    const login = read('features/auth/LoginScreen.tsx');
    const chrome = read('features/auth/AuthChrome.tsx');
    const social = read('features/auth/SocialAuthButtons.tsx');
    const en = read('i18n/locales/en.ts');
    const flow = read('i18n/locales/authFlowEn.ts');
    assert.match(chrome, /LinasSparkleIcon/);
    assert.match(login, /loginWelcome/);
    assert.match(login, /loginTagline/);
    assert.match(en, /loginWelcome: 'Welcome back'/);
    assert.match(en, /loginTagline: 'Log in to Linas AI'/);
    assert.match(login, /onForgotPassword/);
    assert.match(login, /AuthPasswordField/);
    assert.match(login, /continueAsGuestShort/);
    assert.match(login, /LEGAL_URLS\.terms/);
    assert.match(login, /LEGAL_URLS\.privacy/);
    assert.match(social, /logo-google/);
    assert.match(social, /logo-apple/);
    assert.match(social, /styles\.circle/);
    assert.doesNotMatch(social, /comingSoon/);
    assert.doesNotMatch(login, /BrandMark|GradientBackground|Linking\.openURL\(LEGAL_URLS\.forgotPassword\)/);
    assert.match(flow, /continueAsGuestShort: 'Continue as guest'/);
  });
});

describe('create account 3-step flow', () => {
  it('wires credentials + Google/Apple + verify OTP + gender + success', () => {
    const register = read('features/auth/RegisterScreen.tsx');
    const creds = read('features/auth/SignupCredentialsStep.tsx');
    const verify = read('features/auth/SignupVerifyStep.tsx');
    const address = read('features/auth/SignupAddressStep.tsx');
    const success = read('features/auth/SignupSuccessStep.tsx');
    const remote = read('features/auth/authRemote.ts');
    assert.match(creds, /step1of3/);
    assert.match(creds, /createAccount/);
    assert.match(creds, /confirmPassword/);
    assert.match(creds, /passwordHint8/);
    assert.match(creds, /SocialAuthButtons/);
    assert.match(creds, /alreadyHaveAccount/);
    assert.match(verify, /step2of3/);
    assert.match(verify, /verifyYourEmail/);
    assert.match(verify, /AuthOtpRow/);
    assert.match(verify, /verifyEmailCta/);
    assert.match(verify, /resend/);
    assert.match(verify, /changeEmail/);
    assert.match(address, /step3of3/);
    assert.match(address, /howShouldLinasAddress/);
    assert.match(address, /genderMale/);
    assert.match(address, /genderFemale/);
    assert.match(address, /genderUnset/);
    assert.match(success, /youreAllSet/);
    assert.match(success, /continueToLinas/);
    assert.match(register, /registerAccount/);
    assert.match(register, /verifyEmailCode/);
    assert.match(register, /patchOwnerGender/);
    assert.match(register, /mobileLogin/);
    assert.match(remote, /\/api\/auth\/register/);
    assert.match(remote, /\/api\/auth\/verify-email/);
    assert.match(remote, /\/api\/auth\/resend-verification/);
    assert.match(remote, /\/api\/owner-ai\/profile/);
  });
});

describe('forgot password 3-step flow', () => {
  it('wires existing forgot/reset endpoints with 6-digit code', () => {
    const screen = read('features/auth/ForgotPasswordScreen.tsx');
    const email = read('features/auth/ForgotEmailStep.tsx');
    const code = read('features/auth/ForgotCodeStep.tsx');
    const next = read('features/auth/ForgotNewPasswordStep.tsx');
    const remote = read('features/auth/authRemote.ts');
    const tree = read('app/AppScreenTree.tsx');
    const nav = read('app/navigation.ts');
    assert.match(email, /forgotPasswordTitle/);
    assert.match(email, /sendResetCode/);
    assert.match(email, /rememberPassword/);
    assert.match(code, /checkYourEmail/);
    assert.match(code, /AuthOtpRow/);
    assert.match(code, /enter6DigitSentTo/);
    assert.match(next, /createNewPassword/);
    assert.match(next, /resetPasswordCta/);
    assert.match(screen, /requestPasswordReset/);
    assert.match(screen, /resetPasswordWithCode/);
    assert.match(remote, /\/api\/auth\/forgot-password/);
    assert.match(remote, /\/api\/auth\/reset-password/);
    assert.match(nav, /forgot_password/);
    assert.match(tree, /ForgotPasswordScreen/);
    assert.match(tree, /onForgotPassword/);
  });
});

describe('maskEmail + businessNameFromEmail source', () => {
  it('masks local part with five bullets and derives business_name from email', () => {
    const mask = read('features/auth/maskEmail.ts');
    const biz = read('features/auth/businessNameFromEmail.ts');
    assert.match(mask, /\.repeat\(5\)/);
    assert.match(biz, /business_name/);
    assert.match(biz, /slice\(0, 120\)/);
  });
});
