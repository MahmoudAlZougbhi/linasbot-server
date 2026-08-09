import { useState } from "react";
import { PlusIcon } from "@heroicons/react/24/outline";
import CmSectionShell from "./CmSectionShell";
import { asRecordList, newId } from "./cmDraftHelpers";
import { useCmSectionDraft } from "./useCmSectionDraft";

const FIELD_CLASS = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";

const CmHandoffPage = () => {
  const draft = useCmSectionDraft("handoff");
  const contacts = asRecordList(draft.payload.contacts);
  const matrix = asRecordList(draft.payload.matrix);
  const [tab, setTab] = useState(/** @type {"contacts" | "matrix"} */ ("contacts"));

  /**
   * @param {Record<string, unknown>} patch
   */
  const setSection = (patch) => draft.setPayload({ ...draft.payload, ...patch });

  const addContact = () => {
    setSection({
      contacts: [
        {
          id: newId("contact"),
          destination_type: "whatsapp",
          destination_value: "",
          phone_e164: "",
          label: "",
          branch_id: null,
          gender: "any",
          topic_id: null,
          notes: null,
        },
        ...contacts,
      ],
    });
  };

  const addMatrix = () => {
    setSection({
      matrix: [
        {
          id: newId("route"),
          contact_id: contacts[0] ? String(contacts[0].id) : "",
          service_id: null,
          topic_id: null,
          branch_id: null,
          gender: "any",
          enabled: true,
          notes: null,
        },
        ...matrix,
      ],
    });
  };

  /**
   * @param {string} id
   * @param {Record<string, unknown>} patch
   */
  const patchContact = (id, patch) =>
    setSection({
      contacts: contacts.map((item) => (String(item.id) === id ? { ...item, ...patch } : item)),
    });

  /**
   * @param {string} id
   * @param {Record<string, unknown>} patch
   */
  const patchMatrix = (id, patch) =>
    setSection({
      matrix: matrix.map((item) => (String(item.id) === id ? { ...item, ...patch } : item)),
    });

  return (
    <CmSectionShell
      title="Booking & Human Handoff"
      description="Human-contact destinations (phone, WhatsApp, email, or URL) by branch and audience. WhatsApp inbound AI stays disabled — these contacts are outbound handoff only."
      countLabel={`${contacts.length} contacts · ${matrix.length} routes`}
      loading={draft.loading}
      dirty={draft.dirty}
      saving={draft.saving}
      validating={draft.validating}
      conflict={draft.conflict}
      meta={draft.meta}
      validation={draft.validation}
      onReload={() => void draft.load()}
      onSave={() => void draft.save()}
      onValidate={() => void draft.validate()}
    >
      <div className="mb-4 rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
        <label className="block space-y-1">
          <span className="text-sm font-medium text-slate-800">Booking & appointment policy</span>
          <p className="text-xs text-slate-500">
            Appointment, booking-creation, and operational CRM rules redistributed from Knowledge. Original wording is preserved.
          </p>
          <textarea
            className={FIELD_CLASS}
            rows={8}
            value={String(draft.payload.policy_text || "")}
            onChange={(e) => setSection({ policy_text: e.target.value })}
          />
        </label>
      </div>
      <div className="flex gap-2 mb-3">
        <button
          type="button"
          onClick={() => setTab("contacts")}
          className={`rounded-lg px-3 py-1.5 text-sm border ${tab === "contacts" ? "bg-slate-900 text-white border-slate-900" : "border-slate-200"}`}
        >
          Contacts
        </button>
        <button
          type="button"
          onClick={() => setTab("matrix")}
          className={`rounded-lg px-3 py-1.5 text-sm border ${tab === "matrix" ? "bg-slate-900 text-white border-slate-900" : "border-slate-200"}`}
        >
          Routing matrix
        </button>
      </div>

      {tab === "contacts" ? (
        <div className="space-y-3">
          <button type="button" onClick={addContact} className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm text-white">
            <PlusIcon className="w-4 h-4" /> Add contact
          </button>
          {contacts.map((item) => (
            <div key={String(item.id)} className="rounded-2xl border border-slate-200 bg-white p-4 grid sm:grid-cols-2 gap-3">
              <label className="block space-y-1">
                <span className="text-sm font-medium">Label</span>
                <input className={FIELD_CLASS} value={String(item.label || "")} onChange={(e) => patchContact(String(item.id), { label: e.target.value })} />
              </label>
              <label className="block space-y-1">
                <span className="text-sm font-medium">Destination type</span>
                <select
                  className={FIELD_CLASS}
                  value={String(item.destination_type || (item.phone_e164 ? "whatsapp" : "whatsapp"))}
                  onChange={(e) =>
                    patchContact(String(item.id), {
                      destination_type: e.target.value,
                      phone_e164: e.target.value === "whatsapp" || e.target.value === "phone" ? String(item.destination_value || item.phone_e164 || "") : "",
                    })
                  }
                >
                  <option value="whatsapp">WhatsApp / wa.me</option>
                  <option value="phone">Phone</option>
                  <option value="email">Email</option>
                  <option value="url">URL</option>
                </select>
              </label>
              <label className="block space-y-1">
                <span className="text-sm font-medium">Destination value</span>
                <input
                  className={FIELD_CLASS}
                  value={String(item.destination_value || item.phone_e164 || "")}
                  onChange={(e) => {
                    const destination_value = e.target.value;
                    const dtype = String(item.destination_type || "whatsapp");
                    patchContact(String(item.id), {
                      destination_value,
                      phone_e164: dtype === "whatsapp" || dtype === "phone" ? destination_value : "",
                    });
                  }}
                  placeholder={
                    String(item.destination_type || "whatsapp") === "email"
                      ? "hello@example.com"
                      : String(item.destination_type || "whatsapp") === "url"
                        ? "https://example.com/book"
                        : "+9617xxxxxxx"
                  }
                />
              </label>
              <label className="block space-y-1">
                <span className="text-sm font-medium">Branch id</span>
                <input
                  className={FIELD_CLASS}
                  value={String(item.branch_id || "")}
                  onChange={(e) => patchContact(String(item.id), { branch_id: e.target.value || null })}
                />
              </label>
              <label className="block space-y-1">
                <span className="text-sm font-medium">Audience</span>
                <select
                  className={FIELD_CLASS}
                  value={String(item.gender || "any")}
                  onChange={(e) => patchContact(String(item.id), { gender: e.target.value })}
                >
                  <option value="any">Any</option>
                  <option value="female">Female</option>
                  <option value="male">Male</option>
                </select>
              </label>
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          <button type="button" onClick={addMatrix} className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm text-white">
            <PlusIcon className="w-4 h-4" /> Add route
          </button>
          <div className="overflow-auto rounded-2xl border border-slate-200 bg-white">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-left text-slate-600">
                <tr>
                  <th className="px-3 py-2">Contact</th>
                  <th className="px-3 py-2">Branch</th>
                  <th className="px-3 py-2">Audience</th>
                  <th className="px-3 py-2">Enabled</th>
                </tr>
              </thead>
              <tbody>
                {matrix.map((row) => (
                  <tr key={String(row.id)} className="border-t border-slate-100">
                    <td className="px-3 py-2">
                      <select
                        className={FIELD_CLASS}
                        value={String(row.contact_id || "")}
                        onChange={(e) => patchMatrix(String(row.id), { contact_id: e.target.value })}
                      >
                        <option value="">Select…</option>
                        {contacts.map((c) => (
                          <option key={String(c.id)} value={String(c.id)}>
                            {String(c.label || c.id)}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2">
                      <input
                        className={FIELD_CLASS}
                        value={String(row.branch_id || "")}
                        onChange={(e) => patchMatrix(String(row.id), { branch_id: e.target.value || null })}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <select
                        className={FIELD_CLASS}
                        value={String(row.gender || "any")}
                        onChange={(e) => patchMatrix(String(row.id), { gender: e.target.value })}
                      >
                        <option value="any">Any</option>
                        <option value="female">Female</option>
                        <option value="male">Male</option>
                      </select>
                    </td>
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={row.enabled !== false}
                        onChange={(e) => patchMatrix(String(row.id), { enabled: e.target.checked })}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </CmSectionShell>
  );
};

export default CmHandoffPage;
