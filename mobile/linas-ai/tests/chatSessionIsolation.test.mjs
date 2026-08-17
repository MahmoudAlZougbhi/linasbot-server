import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { readChatScreenBundle } from './chatScreenBundle.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

describe('chat session isolation', () => {
  it('logout and cold start rotate guest session before guest UI', () => {
    const shell = read('app/AppShell.tsx');
    const guest = read('auth/guestSession.ts');
    const boot = read('auth/restoreOwnerSession.ts');
    assert.match(guest, /export async function rotateGuestSessionId/);
    assert.match(guest, /export async function rotateGuestSessionOnAppLaunch/);
    assert.match(shell, /rotateGuestSessionOnAppLaunch/);
    assert.match(boot, /await restoreOwnerSession/);
    const restoreAt = boot.indexOf('await restoreOwnerSession');
    const rotateAt = boot.indexOf('await rotateGuest()');
    assert.ok(restoreAt >= 0 && rotateAt > restoreAt, 'owner restore must run before guest rotate');
    assert.match(shell, /await rotateGuestSessionId\(\)/);
    const logout = shell.slice(shell.indexOf('async function logout'));
    const logoutRotateAt = logout.indexOf('await rotateGuestSessionId()');
    const accessAt = logout.indexOf('setHasAccess(false)');
    assert.ok(logoutRotateAt >= 0 && accessAt > logoutRotateAt, 'logout must rotate guest id before guest screen');
    const cleared = shell.slice(shell.indexOf('onAuthCleared'));
    assert.ok(
      cleared.indexOf('rotateGuestSessionId') < cleared.indexOf('setHasAccess(false)'),
      'auth-cleared must rotate guest id before guest screen',
    );
  });

  it('ChatScreen never shows owner transcript while guest', () => {
    const chat = readChatScreenBundle(read);
    assert.match(chat, /useChatSession\(isAuthenticated\)/);
    assert.match(chat, /useGuestChatSession\(!isAuthenticated\)/);
    assert.match(
      chat,
      /const messages = isAuthenticated \? owner\.messages : guest\.messages/,
    );
    assert.match(chat, /guest\.guestId \|\| 'guest'/);
  });

  it('owner bootstrap opens a new chat instead of restoring last thread', () => {
    const session = read('features/chat/useChatSession.ts');
    assert.match(session, /createOwnerConversation/);
    assert.doesNotMatch(session, /preferFresh/);
    assert.doesNotMatch(session, /listed\.conversations\.find/);
    assert.match(session, /mergeListedHistory\(prev, listedHistoryEntries\(listed\.conversations\)\)/);
    assert.doesNotMatch(session, /setHistory\(\(prev\) => \[\{ id: created/);
  });

  it('empty new chats are not inserted into history until first user turn', () => {
    const session = read('features/chat/useChatSession.ts');
    assert.match(session, /upsertStartedHistoryEntry/);
    assert.match(session, /dropUnstartedHistoryEntry/);
    const newChat = session.slice(session.indexOf('async function newChat'));
    assert.doesNotMatch(newChat.slice(0, 800), /setHistory\(\(prev\) => \[\{ id: created/);
    assert.match(session, /appendOptimisticUser/);
    const append = session.slice(session.indexOf('function appendOptimisticUser'));
    assert.match(append.slice(0, 500), /upsertStartedHistoryEntry/);
  });

  it('guest hook clears transcript when auth takes over', () => {
    const guest = read('features/chat/useGuestChatSession.ts');
    assert.match(guest, /if \(!enabled\)/);
    assert.match(guest, /setMessages\(\[\]\)/);
    assert.match(guest, /setGuestId\(null\)/);
  });
});
