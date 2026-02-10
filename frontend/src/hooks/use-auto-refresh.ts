import { useState } from "react";

export function useAutoRefresh(defaultInterval = 10_000) {
  const [enabled, setEnabled] = useState(true);
  const [interval, setIntervalValue] = useState(defaultInterval);

  return {
    refetchInterval: enabled ? interval : false as const,
    enabled,
    interval,
    setEnabled,
    setInterval: setIntervalValue,
  };
}
