import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeftIcon } from "@heroicons/react/24/outline";
import toast from "react-hot-toast";
import { useApi } from "../../hooks/useApi";
import { TABS, emptyLabels } from "./cmPricesHelpers";
import { CmPricesSetupPanels } from "./CmPricesSetupPanels";
import { CmPricesPricingPanels } from "./CmPricesPricingPanels";

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
          <CmPricesSetupPanels
            tab={tab}
            setTab={setTab}
            categories={categories}
            setCategories={setCategories}
            catalog={catalog}
            setCatalog={setCatalog}
            resources={resources}
            setResources={setResources}
            dimensions={dimensions}
            setDimensions={setDimensions}
            addCategory={addCategory}
            addCatalogItem={addCatalogItem}
          />
          <CmPricesPricingPanels
            tab={tab}
            catalog={catalog}
            priceEntries={priceEntries}
            setPriceEntries={setPriceEntries}
            discountRules={discountRules}
            setDiscountRules={setDiscountRules}
            addPriceEntry={addPriceEntry}
            addDiscountRule={addDiscountRule}
            previewItemId={previewItemId}
            setPreviewItemId={setPreviewItemId}
            previewQty={previewQty}
            setPreviewQty={setPreviewQty}
            handlePreviewQuote={handlePreviewQuote}
            quote={quote}
            handleValidate={handleValidate}
            validation={validation}
          />

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
