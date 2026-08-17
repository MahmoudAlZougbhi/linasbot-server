/** Snapshot compare so leave-prompts only fire when payload content changed. */

export function canonicalize(value: unknown): unknown {
  if (value == null) return null;
  if (Array.isArray(value)) return value.map(canonicalize);
  if (typeof value === 'object') {
    const src = value as Record<string, unknown>;
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(src).sort()) {
      out[key] = canonicalize(src[key]);
    }
    return out;
  }
  return value;
}

export function stableSerialize(value: unknown): string {
  return JSON.stringify(canonicalize(value));
}

export function isDraftDirty(baseline: string, payload: unknown): boolean {
  return stableSerialize(payload) !== baseline;
}
