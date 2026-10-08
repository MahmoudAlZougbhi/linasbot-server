// @ts-nocheck
/** @param {{ rows?: number }} props */
export function SkeletonRows({ rows = 6 }) {
  return (
    <div className="space-y-2" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="h-12 animate-pulse rounded-lg bg-slate-200 motion-reduce:animate-none" />
      ))}
    </div>
  );
}
