/** Resolve extensionless relative imports to .ts for node --experimental-strip-types tests. */
import { register } from 'node:module';
import { pathToFileURL } from 'node:url';

register('./resolveTsSiblingHook.mjs', import.meta.url);
