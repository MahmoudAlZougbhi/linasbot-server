import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BookOpenIcon,
  CurrencyDollarIcon,
  SparklesIcon,
} from "@heroicons/react/24/outline";
import ContentFilesPanel from "../components/ContentFilesPanel";

const SECTIONS = [
  { id: "knowledge", name: "Knowledge", icon: BookOpenIcon },
  { id: "price", name: "Prices", icon: CurrencyDollarIcon },
  { id: "style", name: "Style", icon: SparklesIcon },
];

const ContentManagers = () => {
  const [activeSection, setActiveSection] = useState("knowledge");
  const section = SECTIONS.find((s) => s.id === activeSection);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Content Managers</h1>
        <p className="text-slate-600 mt-1">
          Manage Knowledge, Prices, and Style files. The bot uses dynamic retrieval to load only relevant files.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 p-1 bg-slate-100 rounded-xl w-fit">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            onClick={() => setActiveSection(s.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition ${
              activeSection === s.id
                ? "bg-white text-slate-800 shadow-sm"
                : "text-slate-600 hover:text-slate-800"
            }`}
          >
            <s.icon className="w-5 h-5" />
            {s.name}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={activeSection}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.2 }}
        >
          <ContentFilesPanel
            section={section.id}
            sectionName={section.name}
            icon={section.icon}
          />
        </motion.div>
      </AnimatePresence>
    </div>
  );
};

export default ContentManagers;
