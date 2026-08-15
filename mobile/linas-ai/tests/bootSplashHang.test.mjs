/**
 * Splash must always unmount and AppShell must mount chat — never wait on
 * auth/network forever. Source + timing-policy checks (no device required).
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function readSrc(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

/** Mirrors bootSplashTokens.splashExitDelayMs — keep in lockstep with source. */
function splashExitDelayMs(appReady, elapsedMs, minDisplayMs, maxHoldMs) {
  const minWait = Math.max(0, minDisplayMs - elapsedMs);
  const maxWait = Math.max(0, maxHoldMs - elapsedMs);
  return appReady ? minWait : maxWait;
}

describe('splash hang: always reach chat', () => {
  it('exit delay is capped so splash hides without appReady', () => {
    const tokens = readSrc('features/boot/bootSplashTokens.ts');
    assert.match(tokens, /maxHoldMs:\s*2500/);
    assert.match(tokens, /export function splashExitDelayMs/);
    assert.match(tokens, /return appReady \? minWait : maxWait/);
    const minMs = 900;
    const maxHoldMs = 2500;
    assert.equal(splashExitDelayMs(false, 0, minMs, maxHoldMs), maxHoldMs);
    assert.equal(splashExitDelayMs(false, maxHoldMs, minMs, maxHoldMs), 0);
    assert.equal(splashExitDelayMs(false, maxHoldMs + 500, minMs, maxHoldMs), 0);
    assert.equal(splashExitDelayMs(true, 0, minMs, maxHoldMs), minMs);
    assert.equal(splashExitDelayMs(true, minMs, minMs, maxHoldMs), 0);
  });

  it('BootSplash hides native splash without waiting onLayout, and always calls onDone', () => {
    const boot = readSrc('features/boot/BootSplash.tsx');
    assert.match(boot, /splashExitDelayMs/);
    assert.match(boot, /hideNativeSplash\(\),\s*80/);
    assert.match(boot, /SplashScreen\.hideAsync/);
    assert.match(boot, /complete\(\)/);
    assert.doesNotMatch(boot, /if \(finished\) onDone/);
    assert.match(boot, /failsafe = setTimeout\(complete/);
  });

  it('AppShell leaves splash on bootDone alone and always flips authReady', () => {
    const shell = readSrc('app/AppShell.tsx');
    assert.match(shell, /if \(!bootDone\)/);
    assert.doesNotMatch(
      shell,
      /if \(!bootDone \|\| !authReady \|\| screen\.name === 'boot'\)/,
    );
    assert.match(shell, /finally \{\s*setAuthReady\(true\);/);
    assert.doesNotMatch(shell, /if \(!authReady\) return;/);
    assert.match(
      shell,
      /current\.name === 'boot' \? \{ name: 'chat' \} : current/,
    );
    assert.match(shell, /AppScreenTree/);
    assert.match(shell, /<BootSplash appReady=\{authReady\} onDone=\{finishBoot\} \/>/);
  });
});
