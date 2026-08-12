import { PlusIcon, TrashIcon } from "@heroicons/react/24/outline";
import { emptyLabels, labelEn, asRecord } from "./cmPricesHelpers";

/**
 * @param {{
 *   tab: string;
 *   setTab: (tab: string) => void;
 *   categories: Array<Record<string, unknown>>;
 *   setCategories: import('react').Dispatch<import('react').SetStateAction<Array<Record<string, unknown>>>>;
 *   catalog: Array<Record<string, unknown>>;
 *   setCatalog: import('react').Dispatch<import('react').SetStateAction<Array<Record<string, unknown>>>>;
 *   resources: Array<Record<string, unknown>>;
 *   setResources: import('react').Dispatch<import('react').SetStateAction<Array<Record<string, unknown>>>>;
 *   dimensions: Array<Record<string, unknown>>;
 *   setDimensions: import('react').Dispatch<import('react').SetStateAction<Array<Record<string, unknown>>>>;
 *   addCategory: () => void;
 *   addCatalogItem: () => void;
 * }} props
 */
export const CmPricesSetupPanels = ({
  tab,
  setTab,
  categories,
  setCategories,
  catalog,
  setCatalog,
  resources,
  setResources,
  dimensions,
  setDimensions,
  addCategory,
  addCatalogItem,
}) => (
  <>
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

  </>
);
