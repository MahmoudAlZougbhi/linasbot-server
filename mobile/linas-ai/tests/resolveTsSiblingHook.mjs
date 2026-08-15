import { accessSync, constants } from 'node:fs';
import { dirname, join, normalize, relative, resolve as resolvePath, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC_ROOT = normalize(resolvePath(dirname(fileURLToPath(import.meta.url)), '..', 'src'));

function isUnderSrcRoot(absolutePath) {
  const normalized = normalize(absolutePath);
  if (normalized === SRC_ROOT) {
    return true;
  }
  return normalized.startsWith(`${SRC_ROOT}${sep}`);
}

function parentIsUnderSrc(parentURL) {
  if (!parentURL || !parentURL.startsWith('file:')) {
    return false;
  }
  return isUnderSrcRoot(fileURLToPath(parentURL));
}

function hasExplicitExtension(specifier) {
  return /\.(ts|tsx|js|mjs|cjs|json)$/i.test(specifier);
}

function isRelativeExtensionless(specifier) {
  return specifier.startsWith('./') || specifier.startsWith('../');
}

function relativeSpecifier(parentDir, candidatePath) {
  const rel = relative(parentDir, candidatePath);
  if (!rel || rel.startsWith('..')) {
    return null;
  }
  return rel.startsWith('.') ? rel : `./${rel}`;
}

function candidateExists(candidatePath) {
  try {
    accessSync(candidatePath, constants.F_OK);
    return true;
  } catch (err) {
    if (err && typeof err === 'object' && 'code' in err && err.code === 'ENOENT') {
      return false;
    }
    throw err;
  }
}

export async function resolve(specifier, context, nextResolve) {
  if (!isRelativeExtensionless(specifier) || hasExplicitExtension(specifier)) {
    return nextResolve(specifier, context);
  }
  if (!parentIsUnderSrc(context.parentURL)) {
    return nextResolve(specifier, context);
  }

  const parentDir = dirname(fileURLToPath(context.parentURL));
  const base = resolvePath(parentDir, specifier);
  const candidates = [
    `${base}.ts`,
    `${base}.tsx`,
    join(base, 'index.ts'),
    join(base, 'index.tsx'),
  ];

  for (const candidate of candidates) {
    if (!isUnderSrcRoot(candidate)) {
      continue;
    }
    if (!candidateExists(candidate)) {
      continue;
    }
    const resolvedSpecifier = relativeSpecifier(parentDir, candidate);
    if (!resolvedSpecifier) {
      continue;
    }
    return nextResolve(resolvedSpecifier, context);
  }

  return nextResolve(specifier, context);
}
