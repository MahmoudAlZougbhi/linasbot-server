/**
 * Stream stick-to-bottom contracts (no device required).
 *
 * #170: liveText / contentSizeChange must use followBottomIfStuck (never re-arm).
 * Follow-up: onScroll must not re-arm stick while the user is mid-drag/momentum —
 * beginDrag clears stick, but near-bottom onScroll events were flipping it back
 * within NEAR_BOTTOM_PX and stream follow yanked the list down again.
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

describe('stream scroll freedom', () => {
  it('exports followBottomIfStuck that never re-arms stick', () => {
    const hook = read('features/chat/useChatListScroll.ts');
    const marker = 'const followBottomIfStuck = useCallback';
    const start = hook.indexOf(marker);
    assert.ok(start >= 0, 'expected followBottomIfStuck callback');
    const body = hook.slice(start, hook.indexOf('armOpenAtLatest', start));
    assert.doesNotMatch(
      body,
      /stickToBottomRef\.current\s*=\s*true/,
      'followBottomIfStuck must not re-arm stick (that defeats user scroll-away)',
    );
    assert.match(body, /if\s*\(\s*!stickToBottomRef\.current\s*\)\s*return/);
  });

  it('stream growth uses followBottomIfStuck, not scrollToBottom', () => {
    const screen = readChatScreenBundle(read);
    assert.match(screen, /followBottomIfStuck\(false\)/);
    // liveText effect dependency list must drive follow, not scrollToBottom.
    const liveDep = screen.indexOf('turn.liveText,');
    assert.ok(liveDep >= 0);
    const around = screen.slice(Math.max(0, liveDep - 200), liveDep + 200);
    assert.match(around, /followBottomIfStuck/);
    assert.doesNotMatch(around, /scrollToBottom\(false\)/);

    const list = read('features/chat/ChatMessageList.tsx');
    assert.match(list, /onContentSizeChange=\{\(\)\s*=>\s*\{\s*followBottomIfStuck\(false\)/);
    assert.match(list, /onScrollBeginDrag=\{onScrollBeginDrag\}/);
    assert.match(list, /stickToBottomRef\.current\s*=\s*false/);
  });

  it('does not re-arm stick from onScroll during user drag/momentum', () => {
    const list = read('features/chat/ChatMessageList.tsx');
    assert.match(list, /userInteractingRef/);
    assert.match(
      list,
      /nearBottom\s*&&\s*!userInteractingRef\.current/,
      'onScroll must gate stick re-arm on !userInteractingRef',
    );
    assert.match(list, /onScrollEndDrag=\{onScrollEndDrag\}/);
    assert.match(list, /onMomentumScrollEnd=\{onMomentumScrollEnd\}/);
    assert.match(
      list,
      /userInteractingRef\.current\s*=\s*true/,
      'beginDrag must mark interaction so mid-drag onScroll cannot re-arm',
    );
  });

  it('keyboard show still respects stick latch (#144)', () => {
    const hook = read('features/chat/useChatListScroll.ts');
    assert.match(hook, /keyboardWillShow|keyboardDidShow/);
    assert.match(hook, /if\s*\(\s*!stickToBottomRef\.current\s*\)\s*return/);
  });
});
