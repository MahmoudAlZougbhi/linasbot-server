/** @param {string} text */
export function replyHtml(text) {
  const escaped = String(text || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replaceAll('\n', '<br/>');
  return { __html: escaped };
}

/** @param {string} text */
export function detectSourceLanguage(text) {
  const value = String(text || '');
  if (/[\u0600-\u06FF]/.test(value)) return 'ar';
  if (/\b(shou|shu|kif|kifak|howe|huwe|hayda|ma3|taba3|3am|yal[la]?)\b/i.test(value)) return 'franco';
  if (/\b(le|la|les|bonjour|merci|est|une|des)\b/i.test(value)) return 'fr';
  return 'en';
}
