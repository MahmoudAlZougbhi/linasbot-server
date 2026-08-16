import FeatureCarousel from '../FeatureCarousel';
import { TeachAiSetup, TeachKnowledge, TeachOwnerCopilot, TeachProducts, TeachServices } from '../cards/TeachMinis';

const CARDS = [
  {
    id: 'ai-setup',
    title: 'AI Setup',
    description: 'Complete your business profile section by section — guided or manual.',
    Mini: TeachAiSetup,
  },
  {
    id: 'knowledge',
    title: 'Knowledge & Attachments',
    description: 'Teach with text, images, links, documents and videos.',
    Mini: TeachKnowledge,
  },
  {
    id: 'owner-copilot',
    title: 'Owner Copilot',
    description: 'Talk naturally. Linas learns, updates and explains your business with you.',
    core: true,
    Mini: TeachOwnerCopilot,
  },
  {
    id: 'services',
    title: 'Services & Prices',
    description: 'Add every service, price, note and availability rule.',
    Mini: TeachServices,
  },
  {
    id: 'products',
    title: 'Products',
    description: 'Save product details, variants and up to 5 images.',
    Mini: TeachProducts,
  },
];

export default function LandingTeach() {
  return (
    <FeatureCarousel
      id="features"
      kicker="Teach"
      title="Teach Linas once."
      accent="It learns your business."
      subtitle="Use the Owner Copilot or edit every detail yourself — you are always in control."
      cards={CARDS}
    />
  );
}
