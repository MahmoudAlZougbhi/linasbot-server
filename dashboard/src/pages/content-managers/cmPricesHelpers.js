/** Shared helpers for CmPricesPage (LOC split). */

export const TABS = [
  { id: "wizard", label: "Setup Wizard" },
  { id: "catalog", label: "Catalog / Services & Products" },
  { id: "prices", label: "Base Prices & Variants / Matrix" },
  { id: "resources", label: "Options / Machines / Variables" },
  { id: "discounts", label: "Discounts & Packages" },
  { id: "preview", label: "Price Calculator Preview" },
  { id: "validation", label: "Validation & Conflicts" },
  { id: "publish", label: "Version History / Publish" },
];

/** @returns {{ en: string, ar: string, fr: string, franco: string }} */
export const emptyLabels = () => ({ en: "", ar: "", fr: "", franco: "" });

/**
 * @param {unknown} labels
 * @returns {string}
 */
export const labelEn = (labels) => {
  if (!labels || typeof labels !== "object") return "";
  const en = /** @type {{ en?: unknown }} */ (labels).en;
  return typeof en === "string" ? en : "";
};

/**
 * @param {unknown} value
 * @returns {Record<string, unknown>}
 */
export const asRecord = (value) =>
  value && typeof value === "object" ? /** @type {Record<string, unknown>} */ (value) : {};
