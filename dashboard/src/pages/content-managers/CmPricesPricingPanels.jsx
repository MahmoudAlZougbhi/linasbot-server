import { Link } from "react-router-dom";
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  PlusIcon,
} from "@heroicons/react/24/outline";
import { emptyLabels, labelEn, asRecord } from "./cmPricesHelpers";

/**
 * @param {{
 *   tab: string;
 *   catalog: Array<Record<string, unknown>>;
 *   priceEntries: Array<Record<string, unknown>>;
 *   setPriceEntries: import('react').Dispatch<import('react').SetStateAction<Array<Record<string, unknown>>>>;
 *   discountRules: Array<Record<string, unknown>>;
 *   setDiscountRules: import('react').Dispatch<import('react').SetStateAction<Array<Record<string, unknown>>>>;
 *   addPriceEntry: () => void;
 *   addDiscountRule: () => void;
 *   previewItemId: string;
 *   setPreviewItemId: (id: string) => void;
 *   previewQty: string;
 *   setPreviewQty: (qty: string) => void;
 *   handlePreviewQuote: () => void | Promise<void>;
 *   quote: {
 *     subtotal?: number;
 *     discount_amount?: number;
 *     final_total?: number;
 *     currency?: string;
 *     applied_rules?: Array<{ rule_id?: string }>;
 *   } | null;
 *   handleValidate: () => void | Promise<void>;
 *   validation: { ok?: boolean; error_count?: number; errors?: Array<Record<string, unknown>> } | null;
 * }} props
 */
export const CmPricesPricingPanels = ({
  tab,
  catalog,
  priceEntries,
  setPriceEntries,
  discountRules,
  setDiscountRules,
  addPriceEntry,
  addDiscountRule,
  previewItemId,
  setPreviewItemId,
  previewQty,
  setPreviewQty,
  handlePreviewQuote,
  quote,
  handleValidate,
  validation,
}) => (
  <>
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

  </>
);
