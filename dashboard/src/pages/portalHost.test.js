import { describe, expect, it } from 'vitest';
import { isPlatformPortalHost } from './portalHost';

describe('isPlatformPortalHost', () => {
  it('accepts portal hosts', () => {
    expect(isPlatformPortalHost('portal.linasaibot.com')).toBe(true);
    expect(isPlatformPortalHost('www.portal.linasaibot.com')).toBe(true);
    expect(isPlatformPortalHost('WWW.PORTAL.LINASAIBOT.COM')).toBe(true);
  });

  it('rejects marketing and unknown hosts', () => {
    expect(isPlatformPortalHost('linasaibot.com')).toBe(false);
    expect(isPlatformPortalHost('www.linasaibot.com')).toBe(false);
    expect(isPlatformPortalHost('localhost')).toBe(false);
  });
});
