import { HOW_IT_WORKS_STEPS } from '../../constants/landingHowItWorks';

/**
 * Right rail — 01…13 with active pill + label (Karen explore layout).
 * @param {{
 *   index: number,
 *   onSelect: (index: number) => void,
 * }} props
 */
export default function HowItWorksNav({ index, onSelect }) {
  return (
    <nav className="hiw-nav" aria-label="App screens">
      <ol className="hiw-nav-list">
        {HOW_IT_WORKS_STEPS.map((step, i) => {
          const active = i === index;
          return (
            <li key={step.n} className={active ? 'hiw-nav-item is-active' : 'hiw-nav-item'}>
              <button
                type="button"
                className="hiw-nav-btn"
                aria-current={active ? 'step' : undefined}
                aria-label={`${step.n} ${step.navLabel}`}
                onClick={() => onSelect(i)}
              >
                <span className="hiw-nav-num">{step.n}</span>
                {active ? <span className="hiw-nav-label">{step.navLabel}</span> : null}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
