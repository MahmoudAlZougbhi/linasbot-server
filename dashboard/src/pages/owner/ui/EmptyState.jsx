// @ts-nocheck
/** @param {{ icon?: import('react').ReactNode, title: string, text: string, action?: import('react').ReactNode }} props */
export default function EmptyState({ icon, title, text, action }) {
  return (
    <div className="flex flex-col items-center px-4 py-10 text-center">
      {icon ? <div className="grid h-14 w-14 place-items-center rounded-full bg-slate-100 text-slate-600">{icon}</div> : null}
      <h2 className="mt-3 text-base font-semibold text-slate-900">{title}</h2>
      <p className="mt-1 max-w-md text-sm leading-[22px] text-slate-600">{text}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
