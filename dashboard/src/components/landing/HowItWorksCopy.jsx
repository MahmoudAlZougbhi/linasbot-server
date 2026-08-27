import { POINT_ICON_BY_KEY } from './HowItWorksIcons';

/**
 * Left column — step copy + compact point cards (Karen explore layout).
 * @param {{
 *   step: {
 *     n: string,
 *     navLabel: string,
 *     title: string,
 *     body: string,
 *     points: Array<{ icon?: string, title: string }>,
 *   },
 *   total: number,
 * }} props
 */
export default function HowItWorksCopy({ step, total }) {
  return (
    <div className="hiw-copy">
      <p className="hiw-copy-index">
        <span>{step.n}</span>
        <span className="hiw-copy-index-sep"> / {String(total).padStart(2, '0')}</span>
      </p>
      <p className="hiw-copy-nav">{step.navLabel}</p>
      <h3 className="hiw-copy-title">{step.title}</h3>
      <p className="hiw-copy-body">{step.body}</p>
      <div className="hiw-copy-points">
        {step.points.map((point) => {
          const Icon = POINT_ICON_BY_KEY[point.icon || ''] || POINT_ICON_BY_KEY.check;
          return (
            <div key={point.title} className="hiw-point-card">
              <span className="hiw-point-icon">
                <Icon className="h-4 w-4" />
              </span>
              <p className="hiw-point-label">{point.title}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
