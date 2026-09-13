import { describe, expect, it } from 'vitest';
import { isMarketingPublicHost, isPlatformPortalHost } from './portalHost';

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

describe('isMarketingPublicHost', () => {
  it('is only the public marketing site', () => {
    expect(isMarketingPublicHost('linasaibot.com')).toBe(true);
    expect(isMarketingPublicHost('www.linasaibot.com')).toBe(true);
    expect(isMarketingPublicHost('www.portal.linasaibot.com')).toBe(false);
    expect(isMarketingPublicHost('localhost')).toBe(false);
  });
});
