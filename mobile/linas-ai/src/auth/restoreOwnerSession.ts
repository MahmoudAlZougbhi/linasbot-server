export type TokenReader = {
  getAccessToken(): Promise<string | null>;
};

export type RestoreOwnerSessionOptions = {
  attempts?: number;
  delayMs?: number;
  sleep?: (ms: number) => Promise<void>;
};

const DEFAULT_ATTEMPTS = 4;
const DEFAULT_DELAY_MS = 120;

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Read the persisted owner access token. Retries only when SecureStore throws
 * (iOS keychain not ready). A definite null is logged-out — do not wait.
 */
export async function restoreOwnerSession(
  store: TokenReader,
  options: RestoreOwnerSessionOptions = {},
): Promise<boolean> {
  const attempts = options.attempts ?? DEFAULT_ATTEMPTS;
  const delayMs = options.delayMs ?? DEFAULT_DELAY_MS;
  const sleep = options.sleep ?? defaultSleep;

  for (let i = 0; i < attempts; i++) {
    try {
      const access = await store.getAccessToken();
      return Boolean(access);
    } catch {
      if (i < attempts - 1) {
        await sleep(delayMs);
      }
    }
  }
  return false;
}

/**
 * Cold-start auth: restore owner tokens first. Guest rotate never skips
 * setHasAccess. Guests still wait for rotate so they cannot reopen a prior thread.
 */
export async function bootPersistedAuth(
  store: TokenReader,
  rotateGuest: () => Promise<void>,
): Promise<boolean> {
  const hasAccess = await restoreOwnerSession(store);
  if (!hasAccess) {
    try {
      await rotateGuest();
    } catch {
      /* Guest mint failed; guest hook will getOrCreate. Owner session unchanged. */
    }
    return false;
  }
  void rotateGuest().catch(() => {});
  return true;
}
