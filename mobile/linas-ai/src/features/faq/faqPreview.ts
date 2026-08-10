import type { FaqGroup } from './faqApi';

export function variantPreview(group: FaqGroup, preferred = 'en'): string {
  const variants = Array.isArray(group.variants) ? group.variants : [];
  const preferredRow = variants.find((v) => String(v.language) === preferred);
  if (preferredRow && typeof preferredRow.question === 'string' && preferredRow.question.trim()) {
    return preferredRow.question.trim();
  }
  const any = variants.find((v) => typeof v.question === 'string' && String(v.question).trim());
  return any ? String(any.question) : String(group.qa_group_id || 'FAQ');
}

export function variantForLang(group: FaqGroup, language: string) {
  const variants = Array.isArray(group.variants) ? group.variants : [];
  return variants.find((v) => String(v.language) === language) || null;
}
