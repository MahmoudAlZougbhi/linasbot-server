/**
 * Composer + menu: Photos/Files popover, document picker, attach payload.
 * Run: node --test mobile/linas-ai/tests/composerPlusMenu.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = (...p) => join(root, 'src', ...p);

function read(rel) {
  return readFileSync(src(...rel.split('/')), 'utf8');
}

test('plus menu lists Photos and Files only; Files launches document picker', () => {
  const menu = read('features/chat/ComposerPlusMenu.tsx');
  const handler = read('features/chat/handlePlusAction.ts');
  const pick = read('features/chat/v2/pickAttachment.ts');
  const overlays = read('features/chat/ChatScreenOverlays.tsx');
  const send = read('features/chat/sendChatMessage.ts');
  const en = read('i18n/locales/en.ts');
  const ar = read('i18n/locales/ar.ts');
  const fr = read('i18n/locales/fr.ts');

  assert.match(menu, /attach_image/);
  assert.match(menu, /attach_document/);
  assert.match(menu, /tr\('photos'\)/);
  assert.match(menu, /tr\('files'\)/);
  assert.match(menu, /feather\(row\.icon\)/);
  assert.match(menu, /icon: 'image'/);
  assert.match(menu, /icon: 'paperclip'/);
  assert.doesNotMatch(menu, /Plugins|Think harder|attach_camera|launchCamera/);
  assert.match(menu, /onClose\(\)/);
  assert.match(menu, /setTimeout\(\(\) => onAction\(action\)/);

  assert.match(overlays, /ComposerPlusMenu/);
  assert.match(overlays, /handlePlusAction/);
  assert.doesNotMatch(overlays, /ComposerPlusSheet/);

  assert.match(handler, /pickDocumentAttachment/);
  assert.match(handler, /action === 'attach_document'/);
  assert.match(handler, /pickImageAttachments/);

  assert.match(pick, /getDocumentAsync/);
  assert.match(pick, /type:\s*'\*\/\*'/);
  assert.match(pick, /copyToCacheDirectory:\s*true/);
  assert.match(pick, /launchImageLibraryAsync/);

  assert.match(send, /uploadOwnerAttachment/);
  assert.match(send, /attachment_ids: attachmentIds/);
  assert.match(send, /mimeType/);

  assert.match(en, /photos:\s*'Photos'/);
  assert.match(en, /files:\s*'Files'/);
  assert.match(ar, /photos:\s*'الصور'/);
  assert.match(ar, /files:\s*'الملفات'/);
  assert.match(fr, /photos:\s*'Photos'/);
  assert.match(fr, /files:\s*'Fichiers'/);
});
