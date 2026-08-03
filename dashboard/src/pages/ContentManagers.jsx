import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  AcademicCapIcon,
  BookOpenIcon,
  BuildingOffice2Icon,
  ChatBubbleLeftRightIcon,
  ClockIcon,
  CurrencyDollarIcon,
  ExclamationTriangleIcon,
  GlobeAltIcon,
  HandRaisedIcon,
  InboxStackIcon,
  LanguageIcon,
  QuestionMarkCircleIcon,
  RocketLaunchIcon,
  SparklesIcon,
  WrenchScrewdriverIcon,
} from "@heroicons/react/24/outline";
import { CM_SECTION_CARDS } from "./content-managers/cmSections";

/** @type {Record<string, import('react').ComponentType<{ className?: string }>>} */
const SECTION_ICONS = {
  "ai-basics": SparklesIcon,
  languages: LanguageIcon,
  style: AcademicCapIcon,
  "dynamic-messages": ChatBubbleLeftRightIcon,
  services: WrenchScrewdriverIcon,
  branches: BuildingOffice2Icon,
  prices: CurrencyDollarIcon,
  care: HandRaisedIcon,
  knowledge: BookOpenIcon,
  faq: QuestionMarkCircleIcon,
  "learning-inbox": InboxStackIcon,
  handoff: GlobeAltIcon,
  restricted: ExclamationTriangleIcon,
  publish: RocketLaunchIcon,
};

const ContentManagers = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Content Managers</h1>
        <p className="text-slate-600 mt-1 max-w-3xl">
          Guided control plane for Linas AI facts, FAQ, handoff, and restricted topics.
          Edit each section, Save Draft, Validate, then open Preview / Validate / Publish when you
          want customer-facing AI to use the new version.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {CM_SECTION_CARDS.map((card, index) => {
          const Icon = SECTION_ICONS[card.slug] || ClockIcon;
          return (
            <motion.div
              key={card.slug}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, delay: index * 0.03 }}
            >
              <Link
                to={`/content-managers/${card.slug}`}
                className="block h-full rounded-2xl border border-slate-200/80 bg-white/80 backdrop-blur-sm p-5 shadow-sm hover:shadow-md hover:border-slate-300 transition group"
              >
                <div className="flex items-start gap-3">
                  <div className="rounded-xl bg-slate-100 p-2.5 text-slate-700 group-hover:bg-slate-200 transition">
                    <Icon className="w-6 h-6" aria-hidden="true" />
                  </div>
                  <div className="min-w-0">
                    <h2 className="text-base font-semibold text-slate-800">{card.name}</h2>
                    <p className="mt-1 text-sm text-slate-600 leading-relaxed">{card.description}</p>
                  </div>
                </div>
              </Link>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
};

export default ContentManagers;
