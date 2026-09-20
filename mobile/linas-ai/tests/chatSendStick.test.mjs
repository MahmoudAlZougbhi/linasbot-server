/**
 * In-app Sol chat: Send must not bounce the draft, and composing must keep
 * the latest AI bubble on screen (keyboard / abort races).
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';

import { readChatScreenBundle } from './chatScreenBundle.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = (...p) => join(root, 'src', ...p);

function read(rel) {
  return readFileSync(src(...rel.split('/')), 'utf8');
}

describe('in-app chat send + stick', () => {
  it('locks send before the stream token fetch and ignores superseded aborts', () => {
    const stream = read('features/chat/v2/useOwnerStream.ts');
    assert.match(stream, /if \(!notifyCancel\) epochRef\.current \+= 1/);
    const sendAt = stream.indexOf('abortActive(false)');
    const lockAt = stream.indexOf('setStreaming(true)', sendAt);
    const tokenAt = stream.indexOf('ensureAccessToken()', sendAt);
    assert.ok(sendAt >= 0 && lockAt >= 0 && tokenAt > lockAt, 'streaming lock before token');
    assert.match(stream, /if \(!stillOwner\(\)\) \{\s*finish\('cancelled'\)/);
    assert.match(stream, /if \(stillOwner\(\) && notifyCancelRef\.current\)/);
    assert.match(stream, /if \(stillOwner\(\)\) setStreaming\(false\)/);
    assert.doesNotMatch(
      stream.slice(stream.indexOf('const finish =')),
      /else \{\s*setStreaming\(false\);\s*\}/,
    );
  });

  it('composer captures send before keyboard dismiss and swallows iOS draft echo', () => {
    const composer = read('features/chat/ChatComposer.tsx');
    const handleAt = composer.indexOf('function handleSend()');
    const body = composer.slice(handleAt, handleAt + 700);
    assert.match(body, /sendLockRef\.current = true/);
    assert.match(body, /suppressDraftEchoRef\.current = true/);
    assert.ok(body.indexOf('onSend()') < body.indexOf('dismissKeyboard()'));
    assert.match(composer, /if \(suppressDraftEchoRef\.current\) return;/);
    assert.match(composer, /onComposerFocus/);
  });

  it('sendChatMessage raises in-flight for the whole turn', () => {
    const send = read('features/chat/sendChatMessage.ts');
    assert.match(send, /setSendInFlight\?\.\(true\)/);
    assert.match(send, /setSendInFlight\?\.\(false\)/);
    const wrapper = send.slice(
      send.indexOf('export async function sendChatMessage'),
      send.indexOf('async function sendChatMessageOnce'),
    );
    assert.match(wrapper, /finally/);
  });

  it('ChatScreen wires in-flight + composer focus pin + keyboard guard', () => {
    const screen = readChatScreenBundle(read);
    assert.match(screen, /sendInFlight/);
    assert.match(screen, /setSendInFlight/);
    assert.match(screen, /turn\.streaming \|\| sendInFlight/);
    assert.match(screen, /onComposerFocus=\{\(\) => c\.scrollToBottom\(false\)\}/);
    assert.match(screen, /keyboardGuardRef=\{c\.keyboardGuardRef\}/);
  });

  it('list MVCP is only on while loading older, not while composing', () => {
    const list = read('features/chat/ChatMessageList.tsx');
    assert.match(list, /maintainVisibleContentPosition=\{\s*loadingMore \? \{ minIndexForVisible: 0 \} : undefined/);
    assert.match(list, /if \(keyboardGuardRef\?\.current\) return;/);
    assert.match(list, /keyboardGuardRef/);
  });

  it('keyboard show arms a short guard so resize pan cannot drop stick', () => {
    const hook = read('features/chat/useChatListScroll.ts');
    assert.match(hook, /keyboardGuardRef/);
    assert.match(hook, /keyboardGuardRef\.current = true/);
    assert.match(hook, /keyboardGuardRef\.current = false/);
    assert.match(hook, /if\s*\(\s*!stickToBottomRef\.current\s*\)\s*return/);
  });
});
