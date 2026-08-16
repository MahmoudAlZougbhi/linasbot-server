/** Shared Knowledge list/edit helpers for the owner dashboard. */

export const LOCATIONS_KNOWLEDGE_TITLE = "Opening hours & locations";

/**
 * @param {string} title
 */
export function isLocationsKnowledgeTitle(title) {
  const t = String(title || "").trim().toLowerCase();
  return t === "opening hours & locations" || t === "opening hours and locations";
}

/**
 * @param {string} text
 */
export function countWords(text) {
  const trimmed = String(text || "").trim();
  if (!trimmed) return 0;
  return trimmed.split(/\s+/).filter(Boolean).length;
}

/**
 * @param {Record<string, unknown>} att
 */
export function isPdfAttachment(att) {
  const mime = String(att.mime || "").toLowerCase();
  const name = String(att.filename || "").toLowerCase();
  return mime === "application/pdf" || mime.includes("pdf") || name.endsWith(".pdf");
}

/**
 * @param {Record<string, unknown>} att
 */
export function attachmentKind(att) {
  const kind = String(att.kind || "file");
  const mime = String(att.mime || "").toLowerCase();
  if (kind === "link" || String(att.url || "").trim()) return "link";
  if (kind === "video" || mime.startsWith("video/")) return "video";
  if (kind === "image" || mime.startsWith("image/")) return "image";
  return "file";
}

/**
 * @param {unknown} attachments
 */
export function formatMediaSummary(attachments) {
  const rows = Array.isArray(attachments) ? attachments : [];
  let images = 0;
  let videos = 0;
  let pdfs = 0;
  let files = 0;
  let links = 0;
  for (const raw of rows) {
    if (!raw || typeof raw !== "object") continue;
    const att = /** @type {Record<string, unknown>} */ (raw);
    const kind = attachmentKind(att);
    if (kind === "link") links += 1;
    else if (kind === "image") images += 1;
    else if (kind === "video") videos += 1;
    else if (isPdfAttachment(att)) pdfs += 1;
    else files += 1;
  }
  /** @type {string[]} */
  const bits = [];
  /**
   * @param {number} n
   * @param {string} one
   * @param {string} many
   */
  const part = (n, one, many) => {
    if (n > 0) bits.push(`${n} ${n === 1 ? one : many}`);
  };
  part(images, "image", "images");
  part(videos, "video", "videos");
  part(pdfs, "PDF", "PDFs");
  part(files, "file", "files");
  part(links, "link", "links");
  return bits.length ? bits.join(" • ") : "Text only";
}

/**
 * @param {string | null | undefined} iso
 */
export function formatUpdatedStamp(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  if (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  ) {
    return "Updated today";
  }
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `Updated ${months[d.getMonth()]} ${d.getDate()}`;
}

/**
 * @param {string} value
 */
export function isValidHttpUrl(value) {
  try {
    const parsed = new URL(String(value || "").trim());
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}
