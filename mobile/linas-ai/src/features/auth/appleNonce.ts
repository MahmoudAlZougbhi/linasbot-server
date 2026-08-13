import * as Crypto from 'expo-crypto';

/** Cryptographically random nonce string for Sign in with Apple. */
export function randomAppleNonce(bytes = 32): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let out = '';
  const arr = new Uint8Array(bytes);
  Crypto.getRandomValues(arr);
  for (let i = 0; i < arr.length; i++) {
    out += alphabet[arr[i]! % alphabet.length];
  }
  return out;
}

/**
 * SHA-256 hex for ASAuthorizationAppleIDRequest.nonce.
 * Apple returns this value unchanged in the identity token; the backend
 * compares claims.nonce to SHA-256(rawNonce) and must receive the raw nonce.
 */
export async function sha256HexNonce(rawNonce: string): Promise<string> {
  return Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, rawNonce);
}
