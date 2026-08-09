import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

// Mirrors mobile/linas-ai/src/api/networkError.ts for node:test (no TS loader).
function isNetworkFailure(err) {
  if (err == null) return false;
  if (err instanceof TypeError) return true;
  const msg = String(
    typeof err === 'object' && err !== null && 'message' in err ? err.message : err,
  ).toLowerCase();
  return (
    msg === 'stream_network_error' ||
    msg.includes('network request failed') ||
    msg.includes('failed to fetch') ||
    msg.includes('network error') ||
    msg.includes('the internet connection appears to be offline') ||
    msg.includes('nsurlerrordomain')
  );
}

describe('isNetworkFailure', () => {
  it('treats TypeError / RN fetch failures as network', () => {
    assert.equal(isNetworkFailure(new TypeError('Network request failed')), true);
    assert.equal(isNetworkFailure(new Error('Network request failed')), true);
    assert.equal(isNetworkFailure(new Error('Failed to fetch')), true);
    assert.equal(isNetworkFailure('stream_network_error'), true);
  });

  it('does not treat HTTP / auth / app errors as network', () => {
    assert.equal(isNetworkFailure(new Error('stream_http_401')), false);
    assert.equal(isNetworkFailure(new Error('stream_http_404')), false);
    assert.equal(isNetworkFailure(new Error('Not authenticated')), false);
    assert.equal(isNetworkFailure(new Error('upload_failed')), false);
    assert.equal(isNetworkFailure(new Error('Request failed')), false);
  });
});
