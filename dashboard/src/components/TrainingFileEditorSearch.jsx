import { motion, AnimatePresence } from "framer-motion";
import {
  MagnifyingGlassIcon,
  XMarkIcon,
  ChevronUpIcon,
  ChevronDownIcon,
} from "@heroicons/react/24/outline";

/**
 * @param {{
 *   isSearchOpen: boolean;
 *   colors: { helpBg: string; helpBorder: string; helpText: string; bg: string; icon: string };
 *   searchInputRef: import('react').RefObject<HTMLInputElement>;
 *   searchQuery: string;
 *   setSearchQuery: (value: string) => void;
 *   searchResults: Array<{ lineNumber: number; lineContent: string }>;
 *   currentMatchIndex: number;
 *   goToPrevMatch: () => void;
 *   goToNextMatch: () => void;
 *   toggleSearch: () => void;
 *   navigateToMatch: (matchIndex: number) => void;
 * }} props
 */
export const TrainingFileEditorSearch = ({
  isSearchOpen,
  colors,
  searchInputRef,
  searchQuery,
  setSearchQuery,
  searchResults,
  currentMatchIndex,
  goToPrevMatch,
  goToNextMatch,
  toggleSearch,
  navigateToMatch,
}) => (
  <AnimatePresence>
    {isSearchOpen && (
      <motion.div
        initial={{ opacity: 0, height: 0 }}
        animate={{ opacity: 1, height: "auto" }}
        exit={{ opacity: 0, height: 0 }}
        transition={{ duration: 0.2 }}
        className="overflow-hidden"
      >
        <div className={`${colors.helpBg} border ${colors.helpBorder} rounded-lg p-3`}>
          <div className="flex items-center space-x-3">
            <div className="relative flex-1">
              <MagnifyingGlassIcon className="w-4 h-4 absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400" />
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search in content..."
                className="input-field pl-9 pr-4 py-2 w-full text-sm"
              />
            </div>

            {searchQuery && (
              <div className="flex items-center space-x-2">
                <span
                  className={`text-sm font-medium ${
                    searchResults.length > 0 ? colors.helpText : "text-slate-400"
                  }`}
                >
                  {searchResults.length > 0
                    ? `${currentMatchIndex + 1} of ${searchResults.length}`
                    : "No matches"}
                </span>

                {searchResults.length > 0 && (
                  <>
                    <button
                      onClick={goToPrevMatch}
                      className={`p-1.5 rounded-lg ${colors.bg} ${colors.icon} hover:opacity-80 transition-opacity`}
                      title="Previous match (Shift+Enter)"
                    >
                      <ChevronUpIcon className="w-4 h-4" />
                    </button>
                    <button
                      onClick={goToNextMatch}
                      className={`p-1.5 rounded-lg ${colors.bg} ${colors.icon} hover:opacity-80 transition-opacity`}
                      title="Next match (Enter)"
                    >
                      <ChevronDownIcon className="w-4 h-4" />
                    </button>
                  </>
                )}
              </div>
            )}

            <button
              onClick={toggleSearch}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
              title="Close search (Esc)"
            >
              <XMarkIcon className="w-4 h-4" />
            </button>
          </div>

          {searchQuery && searchResults.length > 0 && (
            <div className="mt-3 max-h-40 overflow-y-auto space-y-1">
              {searchResults.slice(0, 10).map((result, idx) => (
                <button
                  key={idx}
                  onClick={() => navigateToMatch(idx)}
                  className={`w-full text-left p-2 rounded-lg text-sm transition-colors ${
                    idx === currentMatchIndex
                      ? `${colors.bg} ${colors.helpText}`
                      : "hover:bg-white/50 text-slate-600"
                  }`}
                >
                  <span className="font-medium text-slate-400 mr-2">
                    Line {result.lineNumber}:
                  </span>
                  <span className="truncate">
                    {result.lineContent.length > 80
                      ? result.lineContent.substring(0, 80) + "..."
                      : result.lineContent}
                  </span>
                </button>
              ))}
              {searchResults.length > 10 && (
                <p className="text-xs text-slate-400 text-center py-1">
                  +{searchResults.length - 10} more matches
                </p>
              )}
            </div>
          )}
        </div>
      </motion.div>
    )}
  </AnimatePresence>
);
