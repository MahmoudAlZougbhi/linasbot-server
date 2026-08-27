import HowItWorksPhone from './HowItWorksPhone';

/**
 * Center stage — phone + soft mint glow only (Karen explore layout).
 * @param {{
 *   step: { n: string, image: string, alt: string, builtScreen?: string },
 * }} props
 */
export default function HowItWorksStage({ step }) {
  return (
    <div className="hiw-stage">
      <span className="hiw-stage-arc" aria-hidden="true" />
      <div className="hiw-device">
        <HowItWorksPhone step={step} />
        <span className="hiw-phone-glow" aria-hidden="true" />
      </div>
    </div>
  );
}
