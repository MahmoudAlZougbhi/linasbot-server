import { useState } from "react";
import { useApiContent } from "./useApiContent";
import { useApiQA } from "./useApiQA";
import { useApiTesting } from "./useApiTesting";
import { useApiTraining } from "./useApiTraining";

export const useApi = () => {
  const [loading, setLoading] = useState(false);
  const [currentProvider, setCurrentProvider] = useState("meta");
  const [botStatus, setBotStatus] = useState(/** @type {BotStatus} */ ({
    status: "unknown",
    uptime: 0,
    responseTime: 0,
    features: [],
    currentProvider: "meta",
  }));

  const testing = useApiTesting({ setLoading, currentProvider, setCurrentProvider, setBotStatus });
  const qa = useApiQA({ setLoading });
  const training = useApiTraining({ setLoading });
  const content = useApiContent();

  return {
    loading,
    currentProvider,
    botStatus,
    ...testing,
    ...qa,
    ...training,
    ...content,
  };
};
