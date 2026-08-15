import { accessSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export async function resolve(specifier, context, nextResolve) {
  if (
    specifier.startsWith('.') &&
    !specifier.endsWith('.ts') &&
    !specifier.endsWith('.tsx') &&
    !specifier.endsWith('.js') &&
    !specifier.endsWith('.mjs')
  ) {
    const parentDir = dirname(fileURLToPath(context.parentURL));
    const tsPath = join(parentDir, `${specifier}.ts`);
    try {
      accessSync(tsPath);
      return nextResolve(`${specifier}.ts`, context);
    } catch {
      // fall through
    }
  }
  return nextResolve(specifier, context);
}
