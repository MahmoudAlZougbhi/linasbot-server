import HowItWorksDashboardScreen from './HowItWorksDashboardScreen';

/**
 * @param {{
 *   step: { n: string, image: string, alt: string, builtScreen?: string },
 * }} props
 */
export default function HowItWorksPhone({ step }) {
  return (
    <div className="hiw-phone-wrap mx-auto">
      <div className="hiw-ghost" aria-hidden="true" />
      <div className="hiw-ghost hiw-ghost-b" aria-hidden="true" />
      <div className="hiw-phone">
        <div className="hiw-phone-screen">
          <span className="hiw-island" />
          {step.builtScreen === 'dashboard' ? (
            <HowItWorksDashboardScreen />
          ) : (
            <img src={step.image} alt={step.alt} className="h-full w-full object-cover object-top" />
          )}
        </div>
      </div>
      <div className="hiw-stand" aria-hidden="true">
        <div className="hiw-stand-top" />
        <div className="hiw-stand-glow" />
      </div>
    </div>
  );
}
