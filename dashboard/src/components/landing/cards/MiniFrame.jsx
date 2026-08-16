import LinasStar from '../LinasStar';

/**
 * @param {{ play?: boolean, children: import('react').ReactNode, className?: string }} props
 */
export default function MiniFrame({ play = false, children, className = '' }) {
  return (
    <div className={`mt-4 rounded-[1.15rem] border border-[#E6EBE8] bg-[#F7F9F7] p-3 ${play ? 'lp-play' : ''} ${className}`}>
      {children}
    </div>
  );
}

export function CoreBadge() {
  return (
    <span className="inline-flex items-center rounded-full bg-[#06715F] px-2 py-0.5 text-[0.58rem] font-bold uppercase tracking-[0.12em] text-white">
      Core feature
    </span>
  );
}

/**
 * @param {{ title: string, description: string, core?: boolean }} props
 */
export function CardHead({ title, description, core = false }) {
  return (
    <div>
      <div className="flex items-start justify-between gap-2">
        <LinasStar className="mt-0.5 h-4 w-4 shrink-0" />
        {core ? <CoreBadge /> : null}
      </div>
      <h3 className="mt-2 text-[1.05rem] font-semibold tracking-tight text-[#171A19]">{title}</h3>
      <p className="mt-1 text-sm leading-snug text-[#6B746F]">{description}</p>
    </div>
  );
}
