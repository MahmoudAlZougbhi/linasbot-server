import {
  BookOpenIcon,
  CurrencyDollarIcon,
  SparklesIcon,
} from "@heroicons/react/24/outline";

/** Icon mapping for different file types */
export const FILE_ICONS = {
  knowledge_base: BookOpenIcon,
  style_guide: SparklesIcon,
  price_list: CurrencyDollarIcon,
};

/** Color configuration for different file types */
export const FILE_COLORS = {
  knowledge_base: {
    icon: "text-blue-600",
    bg: "bg-blue-100",
    helpBg: "bg-blue-50",
    helpBorder: "border-blue-200",
    helpText: "text-blue-800",
  },
  style_guide: {
    icon: "text-purple-600",
    bg: "bg-purple-100",
    helpBg: "bg-purple-50",
    helpBorder: "border-purple-200",
    helpText: "text-purple-800",
  },
  price_list: {
    icon: "text-green-600",
    bg: "bg-green-100",
    helpBg: "bg-green-50",
    helpBorder: "border-green-200",
    helpText: "text-green-800",
  },
};

/** Description/help text for each file type */
export const FILE_HELP_TEXT = {
  knowledge_base:
    "This knowledge base contains information the bot can reference when answering customer questions. Include product details, procedures, FAQs, and any other relevant information.",
  style_guide:
    "These instructions guide the AI's behavior in every customer conversation. The bot reads these guidelines before responding to ensure consistent, professional interactions.",
  price_list:
    "List your service prices here. The bot will reference this when customers ask about pricing. Format: one service per line with price.",
};

/** @param {string | null | undefined} dateString */
export const formatDate = (dateString) => {
  if (!dateString) return "Unknown";
  const date = new Date(dateString);
  return date.toLocaleString();
};

/** @param {number | null | undefined} bytes */
export const formatFileSize = (bytes) => {
  if (!bytes) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
};

/**
 * @param {string} content
 * @param {string} searchQuery
 * @returns {Array<{ index: number; lineNumber: number; lineContent: string; matchText: string }>}
 */
export const findTrainingSearchMatches = (content, searchQuery) => {
  if (!searchQuery.trim() || !content) return [];

  const results = [];
  const searchLower = searchQuery.toLowerCase();
  const contentLower = content.toLowerCase();
  let index = 0;

  while ((index = contentLower.indexOf(searchLower, index)) !== -1) {
    const lineNumber = content.substring(0, index).split("\n").length;
    const lines = content.split("\n");
    const lineContent = lines[lineNumber - 1] || "";

    results.push({
      index,
      lineNumber,
      lineContent: lineContent.trim(),
      matchText: content.substring(index, index + searchQuery.length),
    });
    index += 1;
  }

  return results;
};
