import LinasStar from './LinasStar';

const PATH =
  'M 292 12 C 168 72, 118 128, 168 188 C 228 258, 92 286, 72 348 C 52 414, 248 428, 338 468 C 468 528, 572 508, 548 598 C 522 686, 248 708, 168 778 C 108 838, 238 888, 286 918';

/**
 * @param {{
 *   step: { n: string, kicker: string },
 *   prev?: { n: string, kicker: string } | null,
 *   next?: { n: string, kicker: string } | null,
 * }} props
 */
export default function HowItWorksPath({ step, prev, next }) {
  const prevShow = step.n === '03' ? { n: '02', kicker: 'AI SETUP' } : prev;
  const nextShow = step.n === '03' ? { n: '04', kicker: 'REQUESTS' } : next;

  return (
    <div className="hiw-path-col hidden md:block" aria-hidden="true">
      <svg className="hiw-path" viewBox="0 0 640 920" preserveAspectRatio="none">
        <path className="hiw-path-line hiw-path-line-soft" d={PATH} />
        <path className="hiw-path-line" d={PATH} />
        <circle className="hiw-node hiw-node-dim" cx="168" cy="72" r="4" />
        <circle className="hiw-node" cx="168" cy="188" r="6" />
        <circle className="hiw-node hiw-node-dim" cx="548" cy="598" r="4" />
        <circle className="hiw-node hiw-node-active" cx="72" cy="348" r="7.5" />
        <circle className="hiw-node hiw-node-dim" cx="168" cy="778" r="4" />
        <circle className="hiw-node" cx="286" cy="918" r="5.5" />
      </svg>
      {prevShow ? (
        <p className="hiw-path-caption hiw-path-caption-prev">
          {prevShow.n} {pathTitle(prevShow.kicker)}
        </p>
      ) : null}
      <div className="hiw-path-active">
        <span className="hiw-path-star-bloom" />
        <LinasStar className="hiw-path-star" color="#06715F" showMark={false} />
        <p>
          {step.n} {pathTitle(step.kicker)}
        </p>
      </div>
      {nextShow ? (
        <p className="hiw-path-caption hiw-path-caption-next">
          {nextShow.n} {pathTitle(nextShow.kicker)}
        </p>
      ) : null}
    </div>
  );
}

/** @param {string} value */
function pathTitle(value) {
  const head = value.split('/')[0] ?? value;
  return head
    .trim()
    .split(/\s+/)
    .map((word) => {
      if (word === 'AI' || word === 'Q&A') return word;
      return word.charAt(0) + word.slice(1).toLowerCase();
    })
    .join(' ');
}
