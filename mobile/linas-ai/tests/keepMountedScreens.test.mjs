import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

describe('keep-mounted module screens', () => {
  it('AppShell routes through AppScreenTree with auth epoch remount', () => {
    const shell = read('app/AppShell.tsx');
    const tree = read('app/AppScreenTree.tsx');
    const pane = read('app/KeepMountedPane.tsx');
    assert.match(shell, /authEpoch/);
    assert.match(shell, /bumpAuthEpoch/);
    assert.match(shell, /AppScreenTree/);
    assert.match(pane, /display:\s*'none'/);
    assert.match(pane, /Mount children on first activation/);
    for (const name of [
      'chat',
      'settings',
      'integrations',
      'users',
      'dashboard',
      'billing',
      'usage',
      'livechat',
      'notifications',
      'cm',
      'faq',
    ]) {
      assert.ok(
        tree.includes('KeepMountedPane key={`' + name + '-${authEpoch}`}'),
        'missing keep-mounted pane for ' + name,
      );
    }
    // Dynamic/ephemeral routes still unmount (not keep-mounted).
    assert.equal(tree.includes('KeepMountedPane key={`cm_section'), false);
    assert.equal(tree.includes('KeepMountedPane key={`resource'), false);
    assert.equal(tree.includes('KeepMountedPane key={`login'), false);
  });

  it('App entry stays chat-first via AppShell', () => {
    const app = readFileSync(join(root, 'App.tsx'), 'utf8');
    const shell = read('app/AppShell.tsx');
    assert.match(app, /AppShell/);
    assert.match(shell, /setScreen\(\{ name: 'chat' \}\)/);
    assert.doesNotMatch(app, /CreativeStudio/);
  });
});
