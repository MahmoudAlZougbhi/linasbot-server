import { peekCachedUser } from '../auth/tokenMemory';

/** Cache keys include tenant+user so logout / account switch cannot leak rows. */
export function sessionScopeId(): string {
  const user = peekCachedUser();
  if (!user) return 'anon';
  const tenant = String(user.tenantId || user.tenant_id || '').trim() || 'none';
  return `${tenant}:${user.id}`;
}

export function scopedCacheKey(parts: readonly string[]): string {
  return `${sessionScopeId()}|${parts.join('|')}`;
}
