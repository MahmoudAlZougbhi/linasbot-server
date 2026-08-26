import HowItWorksDashboardScreen from './HowItWorksDashboardScreen';

/**
 * @param {{
 *   step: { n: string, image: string, alt: string, builtScreen?: string },
 * }} props
 */
export default function HowItWorksPhone({ step }) {
  const useBuiltDashboard = step.builtScreen === 'dashboard';

  return (
    <div className="hiw-phone-wrap mx-auto">
      <div className="hiw-phone-aura" aria-hidden="true" />
      <div className="hiw-phone">
        <div className="hiw-phone-screen">
          {useBuiltDashboard ? (
            <HowItWorksDashboardScreen />
          ) : (
            <img
              src={step.image}
              alt={step.alt}
              className="hiw-phone-screen-shot"
              loading="eager"
              decoding="async"
            />
          )}
        </div>
      </div>
    </div>
  );
}
