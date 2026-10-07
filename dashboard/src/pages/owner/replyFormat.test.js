import { describe, expect, it } from 'vitest';
import { detectSourceLanguage, replyHtml } from './replyFormat';

describe('replyHtml', () => {
  it('renders bold and escapes html', () => {
    expect(replyHtml('**x**').__html).toBe('<strong>x</strong>');
    expect(replyHtml('<script>alert(1)</script>').__html).toContain('&lt;script&gt;');
    expect(replyHtml('<script>alert(1)</script>').__html).not.toContain('<script>');
  });
});

describe('detectSourceLanguage', () => {
  it('detects Arabic, Franco, French, and English', () => {
    expect(detectSourceLanguage('ما هو الرمز')).toBe('ar');
    expect(detectSourceLanguage('shou howe el code')).toBe('franco');
    expect(detectSourceLanguage('bonjour, quel est le code')).toBe('fr');
    expect(detectSourceLanguage('what is the code')).toBe('en');
  });
});
