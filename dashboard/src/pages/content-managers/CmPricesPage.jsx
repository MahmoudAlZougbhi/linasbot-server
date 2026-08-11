import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowLeftIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  PlusIcon,
  TrashIcon,
} from "@heroicons/react/24/outline";
import toast from "react-hot-toast";
import { useApi } from "../../hooks/useApi";

const TABS = [
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
const emptyLabels = () => ({ en: "", ar: "", fr: "", franco: "" });

/**
 * @param {unknown} labels
 * @returns {string}
 */
const labelEn = (labels) => {
  if (!labels || typeof labels !== "object") return "";
  const en = /** @type {{ en?: unknown }} */ (labels).en;
  return typeof en === "string" ? en : "";
};

/**
 * @param {unknown} value
 * @returns {Record<string, unknown>}
 */
const asRecord = (value) =>
  value && typeof value === "object" ? /** @type {Record<string, unknown>} */ (value) : {};

const CmPricesPage = () => {
  const { getCmDraft, putCmDraft, validateCmDraft, getCmMeta, quoteCmPricing } = useApi();
  const [tab, setTab] = useState("wizard");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [etag, setEtag] = useState(/** @type {string | null} */ (null));
  const [notes, setNotes] = useState("");
  const [policyText, setPolicyText] = useState("");
  const [categories, setCategories] = useState(/** @type {Array<Record<string, unknown>>} */ ([]));
  const [catalog, setCatalog] = useState(/** @type {Array<Record<string, unknown>>} */ ([]));
  const [priceEntries, setPriceEntries] = useState(/** @type {Array<Record<string, unknown>>} */ ([]));
  const [discountRules, setDiscountRules] = useState(/** @type {Array<Record<string, unknown>>} */ ([]));
  const [resources, setResources] = useState(/** @type {Array<Record<string, unknown>>} */ ([]));
  const [dimensions, setDimensions] = useState(/** @type {Array<Record<string, unknown>>} */ ([]));
  const [legacyItems, setLegacyItems] = useState(/** @type {Array<Record<string, unknown>>} */ ([]));
  const [priceBooks, setPriceBooks] = useState(/** @type {Array<Record<string, unknown>>} */ ([]));
  const [ruleSets, setRuleSets] = useState(/** @type {Array<Record<string, unknown>>} */ ([]));
  const [packageRules, setPackageRules] = useState(/** @type {Array<Record<string, unknown>>} */ ([]));
  const [validation, setValidation] = useState(
    /** @type {{ ok?: boolean; error_count?: number; errors?: Array<Record<string, unknown>> } | null} */ (null)
  );
  const [quote, setQuote] = useState(
    /** @type {{
     *   subtotal?: number;
     *   discount_amount?: number;
     *   final_total?: number;
     *   currency?: string;
     *   applied_rules?: Array<{ rule_id?: string }>;
     * } | null} */ (null)
  );
  const [previewItemId, setPreviewItemId] = useState("");
  const [previewQty, setPreviewQty] = useState("1");
  const [meta, setMeta] = useState(/** @type {Record<string, unknown> | null} */ (null));

  const payload = useMemo(
    () => ({
      categories,
      catalog,
      price_entries: priceEntries,
      discount_rules: discountRules,
      resources,
      dimension_definitions: dimensions,
      // Preserve redistributed / advanced fields — never wipe on discount edits.
      items: legacyItems,
      price_books: priceBooks,
      rule_sets: ruleSets,
      package_rules: packageRules,
      policy_text: policyText || "",
      notes: notes || null,
    }),
    [
      categories,
      catalog,
      priceEntries,
      discountRules,
      resources,
      dimensions,
      legacyItems,
      priceBooks,
      ruleSets,
      packageRules,
      policyText,
      notes,
    ]
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [draftRes, metaRes] = await Promise.all([getCmDraft("prices"), getCmMeta()]);
      setMeta(metaRes || null);
      if (!draftRes?.success || !draftRes.data) {
        toast.error(draftRes?.error || "Failed to load prices draft");
        return;
      }
      const envelope = draftRes.data;
      const raw = envelope.payload ?? envelope.data ?? {};
      const section = raw && typeof raw === "object" ? /** @type {Record<string, unknown>} */ (raw) : {};
      setEtag(typeof draftRes.etag === "string" ? draftRes.etag : envelope.etag || null);
      setNotes(typeof section.notes === "string" ? section.notes : "");
      setPolicyText(typeof section.policy_text === "string" ? section.policy_text : "");
      setCategories(
        Array.isArray(section.categories) ? /** @type {Array<Record<string, unknown>>} */ (section.categories) : []
      );
      setCatalog(Array.isArray(section.catalog) ? /** @type {Array<Record<string, unknown>>} */ (section.catalog) : []);
      setPriceEntries(
        Array.isArray(section.price_entries)
          ? /** @type {Array<Record<string, unknown>>} */ (section.price_entries)
          : []
      );
      setDiscountRules(
        Array.isArray(section.discount_rules)
          ? /** @type {Array<Record<string, unknown>>} */ (section.discount_rules)
          : []
      );
      setResources(
        Array.isArray(section.resources) ? /** @type {Array<Record<string, unknown>>} */ (section.resources) : []
      );
      setDimensions(
        Array.isArray(section.dimension_definitions)
          ? /** @type {Array<Record<string, unknown>>} */ (section.dimension_definitions)
          : []
      );
      setLegacyItems(
        Array.isArray(section.items) ? /** @type {Array<Record<string, unknown>>} */ (section.items) : []
      );
      setPriceBooks(
        Array.isArray(section.price_books)
          ? /** @type {Array<Record<string, unknown>>} */ (section.price_books)
          : []
      );
      setRuleSets(
        Array.isArray(section.rule_sets) ? /** @type {Array<Record<string, unknown>>} */ (section.rule_sets) : []
      );
      setPackageRules(
        Array.isArray(section.package_rules)
          ? /** @type {Array<Record<string, unknown>>} */ (section.package_rules)
          : []
      );
      const firstCatalog = Array.isArray(section.catalog) ? section.catalog[0] : null;
      if (
        !previewItemId &&
        firstCatalog &&
        typeof firstCatalog === "object" &&
        firstCatalog !== null &&
        "id" in firstCatalog
      ) {
        setPreviewItemId(String(/** @type {{ id: unknown }} */ (firstCatalog).id));
      }
    } finally {
      setLoading(false);
    }
  }, [getCmDraft, getCmMeta, previewItemId]);

  useEffect(() => {
    void load();
    // intentionally once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSave = async () => {
    if (!etag) {
      toast.error("Missing draft version token");
      return;
    }
    setSaving(true);
    try {
      const result = await putCmDraft("prices", { payload }, etag);
      if (!result?.success) {
        toast.error(result?.error || "Save failed");
        return;
      }
      toast.success("Prices draft saved");
      await load();
    } finally {
      setSaving(false);
    }
  };

  const handleValidate = async () => {
    const result = await validateCmDraft({ section: "prices", payload });
    setValidation(result);
    if (result?.ok) {
      toast.success("Validation passed");
      return;
    }
    const first = Array.isArray(result?.errors) ? result.errors[0] : null;
    const detail =
      first && typeof first === "object"
        ? String(/** @type {{ message?: unknown }} */ (first).message || "")
        : "";
    toast.error(
      detail
        ? `Validation failed: ${detail}`
        : `${result?.error_count || 0} validation error(s) — open Validation tab for details`
    );
  };

  const handlePreviewQuote = async () => {
    if (!previewItemId) {
      toast.error("Select a catalog item");
      return;
    }
    const result = await quoteCmPricing({
      source: "draft",
      lines: [{ catalog_item_id: previewItemId, quantity: Number(previewQty) || 1 }],
    });
    if (!result?.success) {
      toast.error(result?.message || result?.error || "Quote failed");
      setQuote(null);
      return;
    }
    setQuote(result.data || null);
    toast.success("Quote computed");
  };

  const addCatalogItem = () => {
    const id = `item_${Date.now().toString(36)}`;
    setCatalog((prev) => [
      ...prev,
      {
        id,
        item_type: "custom",
        category_ids: categories[0]?.id ? [String(categories[0].id)] : [],
        labels: emptyLabels(),
        aliases: [],
        description: "",
        base_price: null,
        currency: "USD",
        variants: [],
        branch_ids: [],
        audience: "any",
        discount_eligible: true,
        active: true,
        effective: { start: null, end: null },
        provenance: "web_cm",
        revision: 1,
        notes: null,
      },
    ]);
    setPreviewItemId(id);
    setTab("catalog");
  };

  const addCategory = () => {
    const id = `cat_${Date.now().toString(36)}`;
    setCategories((prev) => [
      ...prev,
      { id, labels: { ...emptyLabels(), en: "New category" }, parent_id: null, active: true, notes: null },
    ]);
  };

  const addPriceEntry = () => {
    const first = catalog[0];
    if (!first) {
      toast.error("Add a catalog item first");
      return;
    }
    const itemId = String(first.id);
    setPriceEntries((prev) => [
      ...prev,
      {
        id: `pe_${Date.now().toString(36)}`,
        catalog_item_id: itemId,
        variant_id: null,
        amount: 0,
        currency: "USD",
        branch_id: null,
        audience: "any",
        active: true,
        effective: { start: null, end: null },
        provenance: "web_cm",
        revision: 1,
        notes: null,
        dimensions: {},
      },
    ]);
    setTab("prices");
  };

  const addDiscountRule = () => {
    setDiscountRules((prev) => [
      ...prev,
      {
        id: `rule_${Date.now().toString(36)}`,
        labels: { ...emptyLabels(), en: "New discount" },
        priority: 100,
        stacking: "exclusive",
        exclusive: true,
        when: {
          op: "and",
          conditions: [
            {
              kind: "subtotal_at_least",
              amount: 100,
              count: null,
              item_ids: [],
              category_ids: [],
              branch_ids: [],
              audiences: [],
            },
          ],
          groups: [],
        },
        then: { kind: "percent_off", percent: 10, amount: null, currency: null },
        eligible_item_ids: [],
        excluded_item_ids: [],
        eligible_category_ids: [],
        excluded_category_ids: [],
        currency: "USD",
        rounding: "nearest_0_01",
        min_discount: null,
        max_discount: null,
        active: true,
        effective: { start: null, end: null },
        provenance: "web_cm",
        revision: 1,
        notes: null,
      },
    ]);
    setTab("discounts");
  };

  return (
    <div className="space-y-6">
      <div>
        <Link
          to="/content-managers"
          className="inline-flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-800 mb-2"
        >
          <ArrowLeftIcon className="w-4 h-4" />
          AI Setup
        </Link>
        <h1 className="text-2xl font-bold text-slate-800">Prices</h1>
        <p className="text-slate-600 mt-1 max-w-3xl">
          Configure your catalog, base prices, and discount packages. No code or formulas — use the visual WHEN /
          THEN rules. Notes never override structured amounts.
        </p>
        {meta?.publish_enabled ? (
          <p className="text-sm text-emerald-700 mt-2">
            Publishing enabled · runtime {String(meta.runtime_mode || "unknown")}
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`rounded-full px-3 py-1.5 text-sm border ${
              tab === t.id ? "bg-slate-800 text-white border-slate-800" : "bg-white text-slate-700 border-slate-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-sm text-slate-600 py-12 text-center">Loading prices…</div>
      ) : (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          {tab === "wizard" && (
            <section className="rounded-2xl border bg-white p-5 space-y-3 text-sm text-slate-700">
              <h2 className="text-lg font-medium text-slate-900">Pricing setup wizard</h2>
              <ol className="list-decimal pl-5 space-y-2">
                <li>Add categories and catalog items (services, products, packages, body areas as data, etc.).</li>
                <li>Set base prices and variants in the price matrix — notes never override amounts.</li>
                <li>Optionally define machines/resources and typed variables for your business.</li>
                <li>Build WHEN / THEN discount or package rules visually (no formulas or code).</li>
                <li>Preview with the same engine production uses, then Validate → Publish.</li>
              </ol>
              <div className="flex flex-wrap gap-2 pt-2">
                <button type="button" onClick={() => setTab("catalog")} className="rounded-xl bg-slate-900 text-white px-3 py-2">
                  Start with catalog
                </button>
                <button type="button" onClick={() => setTab("preview")} className="rounded-xl border px-3 py-2">
                  Open calculator
                </button>
              </div>
            </section>
          )}
          {tab === "resources" && (
            <section className="space-y-4">
              <div className="flex gap-2 flex-wrap">
                <button
                  type="button"
                  onClick={() =>
                    setResources((prev) => [
                      ...prev,
                      {
                        id: `res_${Date.now()}`,
                        labels: emptyLabels(),
                        resource_kind: "machine",
                        aliases: [],
                        active: true,
                      },
                    ])
                  }
                  className="inline-flex items-center gap-1 rounded-xl bg-slate-800 text-white px-3 py-2 text-sm"
                >
                  <PlusIcon className="w-4 h-4" /> Resource / machine
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setDimensions((prev) => [
                      ...prev,
                      {
                        id: `dim_${Date.now()}`,
                        labels: emptyLabels(),
                        value_type: "enum",
                        allowed_values: [],
                        required: false,
                        active: true,
                      },
                    ])
                  }
                  className="inline-flex items-center gap-1 rounded-xl border px-3 py-2 text-sm"
                >
                  <PlusIcon className="w-4 h-4" /> Variable / dimension
                </button>
              </div>
              {resources.map((res, idx) => (
                <div key={String(res.id)} className="rounded-xl border bg-white p-4 space-y-2">
                  <div className="text-xs font-medium text-slate-500">ResourceOrMethod</div>
                  <input
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    value={labelEn(res.labels)}
                    placeholder="Display name"
                    onChange={(e) => {
                      const next = [...resources];
                      next[idx] = { ...res, labels: { ...emptyLabels(), ...(res.labels || {}), en: e.target.value } };
                      setResources(next);
                    }}
                  />
                  <input
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    value={String(res.resource_kind || "")}
                    placeholder="Kind (machine, room, staff…)"
                    onChange={(e) => {
                      const next = [...resources];
                      next[idx] = { ...res, resource_kind: e.target.value };
                      setResources(next);
                    }}
                  />
                </div>
              ))}
              {dimensions.map((dim, idx) => (
                <div key={String(dim.id)} className="rounded-xl border bg-white p-4 space-y-2">
                  <div className="text-xs font-medium text-slate-500">Pricing dimension</div>
                  <input
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    value={labelEn(dim.labels)}
                    placeholder="Variable name"
                    onChange={(e) => {
                      const next = [...dimensions];
                      next[idx] = { ...dim, labels: { ...emptyLabels(), ...(dim.labels || {}), en: e.target.value } };
                      setDimensions(next);
                    }}
                  />
                  <select
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    value={String(dim.value_type || "string")}
                    onChange={(e) => {
                      const next = [...dimensions];
                      next[idx] = { ...dim, value_type: e.target.value };
                      setDimensions(next);
                    }}
                  >
                    <option value="string">Text</option>
                    <option value="number">Number</option>
                    <option value="enum">List of values</option>
                    <option value="boolean">Yes / No</option>
                  </select>
                </div>
              ))}
              {!resources.length && !dimensions.length ? (
                <div className="text-sm text-slate-500">No machines or variables yet — optional for simple catalogs.</div>
              ) : null}
            </section>
          )}
          {tab === "catalog" && (
            <section className="space-y-4">
              <div className="flex gap-2 flex-wrap">
                <button
                  type="button"
                  onClick={addCategory}
                  className="inline-flex items-center gap-1 rounded-xl border px-3 py-2 text-sm"
                >
                  <PlusIcon className="w-4 h-4" /> Category
                </button>
                <button
                  type="button"
                  onClick={addCatalogItem}
                  className="inline-flex items-center gap-1 rounded-xl bg-slate-800 text-white px-3 py-2 text-sm"
                >
                  <PlusIcon className="w-4 h-4" /> Catalog item
                </button>
              </div>
              <div className="grid gap-3">
                {categories.map((cat, idx) => (
                  <div key={String(cat.id)} className="rounded-xl border bg-white p-4 space-y-2">
                    <div className="text-xs font-medium text-slate-500">Category</div>
                    <input
                      className="w-full rounded-lg border px-3 py-2 text-sm"
                      value={labelEn(cat.labels)}
                      onChange={(e) => {
                        const next = [...categories];
                        next[idx] = {
                          ...cat,
                          labels: { ...emptyLabels(), ...asRecord(cat.labels), en: e.target.value },
                        };
                        setCategories(next);
                      }}
                      placeholder="Category name (English)"
                    />
                  </div>
                ))}
                {catalog.map((item, idx) => (
                  <div key={String(item.id)} className="rounded-xl border bg-white p-4 space-y-2">
                    <div className="flex justify-between gap-2">
                      <div className="text-xs font-medium text-slate-500">
                        Item · {String(item.item_type || "custom")}
                      </div>
                      <button
                        type="button"
                        className="text-rose-600"
                        onClick={() => setCatalog((prev) => prev.filter((_, i) => i !== idx))}
                        aria-label="Remove item"
                      >
                        <TrashIcon className="w-4 h-4" />
                      </button>
                    </div>
                    <input
                      className="w-full rounded-lg border px-3 py-2 text-sm"
                      value={labelEn(item.labels)}
                      onChange={(e) => {
                        const next = [...catalog];
                        next[idx] = {
                          ...item,
                          labels: { ...emptyLabels(), ...asRecord(item.labels), en: e.target.value },
                        };
                        setCatalog(next);
                      }}
                      placeholder="Display name"
                    />
                    <input
                      className="w-full rounded-lg border px-3 py-2 text-sm"
                      value={Array.isArray(item.aliases) ? item.aliases.map(String).join(", ") : ""}
                      onChange={(e) => {
                        const next = [...catalog];
                        next[idx] = {
                          ...item,
                          aliases: e.target.value
                            .split(",")
                            .map((s) => s.trim())
                            .filter(Boolean),
                        };
                        setCatalog(next);
                      }}
                      placeholder="Aliases / synonyms (comma-separated)"
                    />
                    <div className="grid grid-cols-2 gap-2">
                      <select
                        className="rounded-lg border px-3 py-2 text-sm"
                        value={String(item.item_type || "custom")}
                        onChange={(e) => {
                          const next = [...catalog];
                          next[idx] = { ...item, item_type: e.target.value };
                          setCatalog(next);
                        }}
                      >
                        {[
                          "service",
                          "product",
                          "procedure",
                          "body_area",
                          "appointment_type",
                          "membership",
                          "class",
                          "package",
                          "add_on",
                          "custom",
                        ].map((t) => (
                          <option key={t} value={t}>
                            {t}
                          </option>
                        ))}
                      </select>
                      <input
                        type="number"
                        className="rounded-lg border px-3 py-2 text-sm"
                        value={item.base_price == null ? "" : String(item.base_price)}
                        onChange={(e) => {
                          const next = [...catalog];
                          next[idx] = {
                            ...item,
                            base_price: e.target.value === "" ? null : Number(e.target.value),
                          };
                          setCatalog(next);
                        }}
                        placeholder="Base price (optional)"
                      />
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {tab === "prices" && (
            <section className="space-y-4">
              <button
                type="button"
                onClick={addPriceEntry}
                className="inline-flex items-center gap-1 rounded-xl bg-slate-800 text-white px-3 py-2 text-sm"
              >
                <PlusIcon className="w-4 h-4" /> Price row
              </button>
              {priceEntries.map((entry, idx) => (
                <div key={String(entry.id)} className="rounded-xl border bg-white p-4 grid md:grid-cols-3 gap-2">
                  <select
                    className="rounded-lg border px-3 py-2 text-sm"
                    value={String(entry.catalog_item_id || "")}
                    onChange={(e) => {
                      const next = [...priceEntries];
                      next[idx] = { ...entry, catalog_item_id: e.target.value };
                      setPriceEntries(next);
                    }}
                  >
                    {catalog.map((c) => (
                      <option key={String(c.id)} value={String(c.id)}>
                        {labelEn(c.labels) || String(c.id)}
                      </option>
                    ))}
                  </select>
                  <input
                    type="number"
                    className="rounded-lg border px-3 py-2 text-sm"
                    value={Number(entry.amount || 0)}
                    onChange={(e) => {
                      const next = [...priceEntries];
                      next[idx] = { ...entry, amount: Number(e.target.value) };
                      setPriceEntries(next);
                    }}
                  />
                  <input
                    className="rounded-lg border px-3 py-2 text-sm"
                    value={String(entry.currency || "USD")}
                    onChange={(e) => {
                      const next = [...priceEntries];
                      next[idx] = { ...entry, currency: e.target.value };
                      setPriceEntries(next);
                    }}
                  />
                </div>
              ))}
            </section>
          )}

          {tab === "discounts" && (
            <section className="space-y-4">
              <button
                type="button"
                onClick={addDiscountRule}
                className="inline-flex items-center gap-1 rounded-xl bg-slate-800 text-white px-3 py-2 text-sm"
              >
                <PlusIcon className="w-4 h-4" /> Discount / package rule
              </button>
              {discountRules.map((rule, idx) => {
                const when = asRecord(rule.when);
                const conditions = Array.isArray(when.conditions)
                  ? /** @type {Array<Record<string, unknown>>} */ (when.conditions)
                  : [];
                const cond = conditions[0] || {};
                const then = asRecord(rule.then);
                return (
                  <div key={String(rule.id)} className="rounded-xl border bg-white p-4 space-y-3">
                    <input
                      className="w-full rounded-lg border px-3 py-2 text-sm"
                      value={labelEn(rule.labels)}
                      onChange={(e) => {
                        const next = [...discountRules];
                        next[idx] = {
                          ...rule,
                          labels: { ...emptyLabels(), ...asRecord(rule.labels), en: e.target.value },
                        };
                        setDiscountRules(next);
                      }}
                      placeholder="Rule name"
                    />
                    <p className="text-sm text-slate-600">
                      WHEN subtotal ≥{" "}
                      <input
                        type="number"
                        className="w-24 rounded border px-2 py-1 text-sm mx-1"
                        value={Number(cond.amount || 0)}
                        onChange={(e) => {
                          const next = [...discountRules];
                          const nextConditions = [...conditions];
                          nextConditions[0] = {
                            ...(nextConditions[0] || { kind: "subtotal_at_least" }),
                            kind: "subtotal_at_least",
                            amount: Number(e.target.value),
                          };
                          next[idx] = {
                            ...rule,
                            when: {
                              ...when,
                              op: when.op || "and",
                              conditions: nextConditions,
                              groups: when.groups || [],
                            },
                          };
                          setDiscountRules(next);
                        }}
                      />{" "}
                      THEN{" "}
                      <select
                        className="rounded border px-2 py-1 text-sm mx-1"
                        value={String(then.kind || "percent_off")}
                        onChange={(e) => {
                          const next = [...discountRules];
                          next[idx] = { ...rule, then: { ...then, kind: e.target.value } };
                          setDiscountRules(next);
                        }}
                      >
                        <option value="percent_off">% off</option>
                        <option value="fixed_amount_off">fixed amount off</option>
                        <option value="fixed_final_total">fixed final total</option>
                        <option value="bundle_price">bundle price</option>
                      </select>
                      <input
                        type="number"
                        className="w-24 rounded border px-2 py-1 text-sm mx-1"
                        value={Number(then.percent ?? then.amount ?? 0)}
                        onChange={(e) => {
                          const next = [...discountRules];
                          const kind = String(then.kind || "percent_off");
                          /** @type {Record<string, unknown>} */
                          const nextThen = { ...then, kind };
                          if (kind === "percent_off") nextThen.percent = Number(e.target.value);
                          else nextThen.amount = Number(e.target.value);
                          next[idx] = { ...rule, then: nextThen };
                          setDiscountRules(next);
                        }}
                      />
                    </p>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <label className="flex items-center gap-2">
                        Priority
                        <input
                          type="number"
                          className="rounded border px-2 py-1 w-20"
                          value={Number(rule.priority || 100)}
                          onChange={(e) => {
                            const next = [...discountRules];
                            next[idx] = { ...rule, priority: Number(e.target.value) };
                            setDiscountRules(next);
                          }}
                        />
                      </label>
                      <select
                        className="rounded border px-2 py-1"
                        value={String(rule.stacking || "exclusive")}
                        onChange={(e) => {
                          const next = [...discountRules];
                          next[idx] = {
                            ...rule,
                            stacking: e.target.value,
                            exclusive: e.target.value === "exclusive",
                          };
                          setDiscountRules(next);
                        }}
                      >
                        <option value="exclusive">Exclusive</option>
                        <option value="stack">Stack</option>
                        <option value="best_of">Best of</option>
                      </select>
                    </div>
                  </div>
                );
              })}
            </section>
          )}

          {tab === "preview" && (
            <section className="rounded-xl border bg-white p-4 space-y-3">
              <div className="grid md:grid-cols-3 gap-2">
                <select
                  className="rounded-lg border px-3 py-2 text-sm"
                  value={previewItemId}
                  onChange={(e) => setPreviewItemId(e.target.value)}
                >
                  <option value="">Select item</option>
                  {catalog.map((c) => (
                    <option key={String(c.id)} value={String(c.id)}>
                      {labelEn(c.labels) || String(c.id)}
                    </option>
                  ))}
                </select>
                <input
                  className="rounded-lg border px-3 py-2 text-sm"
                  type="number"
                  value={previewQty}
                  onChange={(e) => setPreviewQty(e.target.value)}
                  placeholder="Quantity"
                />
                <button
                  type="button"
                  onClick={() => void handlePreviewQuote()}
                  className="rounded-xl bg-slate-800 text-white px-3 py-2 text-sm"
                >
                  Calculate
                </button>
              </div>
              {quote ? (
                <div className="text-sm space-y-1">
                  <p>
                    Subtotal: {String(quote.subtotal)} {String(quote.currency)}
                  </p>
                  <p>
                    Discount: {String(quote.discount_amount)} {String(quote.currency)}
                  </p>
                  <p className="font-semibold">
                    Final: {String(quote.final_total)} {String(quote.currency)}
                  </p>
                  <p className="text-slate-500">
                    Applied rules: {(quote.applied_rules || []).map((r) => r.rule_id).join(", ") || "none"}
                  </p>
                </div>
              ) : (
                <p className="text-sm text-slate-500">Run a preview to see the deterministic quote.</p>
              )}
            </section>
          )}

          {tab === "validation" && (
            <section className="rounded-xl border bg-white p-4 space-y-3">
              <button type="button" onClick={() => void handleValidate()} className="rounded-xl border px-3 py-2 text-sm">
                Validate prices
              </button>
              {validation ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    {validation.ok ? (
                      <CheckCircleIcon className="w-5 h-5 text-emerald-600" />
                    ) : (
                      <ExclamationTriangleIcon className="w-5 h-5 text-rose-600" />
                    )}
                    Validation {validation.ok ? "passed" : "failed"}
                  </div>
                  {(validation.errors || []).map((err, i) => (
                    <p key={i} className="text-sm text-rose-700">
                      {String(err.message || err.code || "Error")}
                    </p>
                  ))}
                </div>
              ) : null}
            </section>
          )}

          {tab === "publish" && (
            <section className="rounded-xl border bg-white p-4 space-y-2 text-sm text-slate-700">
              <p>
                Save this draft, validate, then publish from the Publish page to activate a new immutable version for
                customers.
              </p>
              <Link to="/content-managers/publish" className="inline-flex rounded-xl bg-emerald-700 text-white px-3 py-2">
                Open Publish
              </Link>
            </section>
          )}

          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700">Price policy (redistributed text)</span>
            <textarea
              value={policyText}
              onChange={(e) => setPolicyText(e.target.value)}
              rows={5}
              className="w-full rounded-xl border px-3 py-2 text-sm"
              placeholder="Recovered pricing guidance text. Structured amounts above always win — never invent numbers here."
            />
          </label>

          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700">Author notes</span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="w-full rounded-xl border px-3 py-2 text-sm"
              placeholder="Notes never override structured prices or discount math."
            />
          </label>

          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={saving}
              className="rounded-xl bg-slate-800 text-white px-4 py-2.5 text-sm disabled:opacity-60"
            >
              {saving ? "Saving…" : "Save Draft"}
            </button>
            <button type="button" onClick={() => void handleValidate()} className="rounded-xl border px-4 py-2.5 text-sm">
              Validate
            </button>
          </div>
        </motion.div>
      )}
    </div>
  );
};

export default CmPricesPage;
