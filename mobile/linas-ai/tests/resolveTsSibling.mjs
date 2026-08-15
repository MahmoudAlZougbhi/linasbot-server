/** Register extensionless sibling resolution for node --experimental-strip-types tests. */
import { register } from 'node:module';

register('./resolveTsSiblingHook.mjs', import.meta.url);
