// @ts-nocheck
/** @param {{ text?: string, children?: import('react').ReactNode }} props */
export default function TechDetails({ text, children }) {
  const value = text || '';
  return (
    <details data-tech-details className="mt-3 rounded-lg bg-slate-100 p-3 text-[13px] text-slate-700">
      <summary className="cursor-pointer font-medium text-slate-700">Technical details</summary>
      <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap font-mono [overflow-wrap:anywhere]">{children || value}</pre>
      <button
        type="button"
        className="mt-2 text-sm font-medium text-[#0F766E]"
        onClick={() => { void navigator.clipboard?.writeText(value); }}
      >
        Copy
      </button>
    </details>
  );
}
