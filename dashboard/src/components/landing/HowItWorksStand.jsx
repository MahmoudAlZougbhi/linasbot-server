import { LANDING_ASSETS } from '../../constants/landingDesignAssets';

/** Glowing podium under the How-it-works phone (Karen scroll stage). */
export default function HowItWorksStand() {
  return (
    <div className="hiw-podium" aria-hidden="true">
      <span className="hiw-podium-glow" />
      <img
        className="hiw-podium-img"
        src={LANDING_ASSETS.howItWorksPodium}
        alt=""
        decoding="async"
        draggable={false}
      />
    </div>
  );
}
