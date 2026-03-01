import React from "react";
import { CheckCircleIcon, ClockIcon, UserIcon } from "@heroicons/react/24/outline";

const statusBadges = {
  bot: {
    color: "bg-blue-100 text-blue-700",
    icon: CheckCircleIcon,
    text: "Bot Handling",
  },
  human: {
    color: "bg-green-100 text-green-700",
    icon: UserIcon,
    text: "Human Handling",
  },
  waiting_human: {
    color: "bg-orange-100 text-orange-700",
    icon: ClockIcon,
    text: "Waiting",
  },
  resolved: {
    color: "bg-slate-100 text-slate-700",
    icon: CheckCircleIcon,
    text: "Resolved",
  },
};

const sentimentIndicators = {
  positive: { color: "text-green-500", emoji: "😊" },
  neutral: { color: "text-slate-500", emoji: "😐" },
  negative: { color: "text-red-500", emoji: "😟" },
};

export const StatusBadge = ({ status }) => {
  const badge = statusBadges[status] || statusBadges.bot;
  const Icon = badge.icon;
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${badge.color}`}
    >
      <Icon className="w-3 h-3 mr-1" />
      {badge.text}
    </span>
  );
};

export const SentimentIndicator = ({ sentiment }) => {
  const indicator = sentimentIndicators[sentiment] || sentimentIndicators.neutral;
  return (
    <span className={`text-lg ${indicator.color}`} title={sentiment}>
      {indicator.emoji}
    </span>
  );
};
