import { useCallback, useEffect, useRef, useState } from "react";

type AutoRefreshOptions = {
  enabled?: boolean;
  interval?: number; // in milliseconds
  onRefresh: () => void | Promise<void>;
};

export function useAutoRefresh({ enabled = false, interval = 30000, onRefresh }: AutoRefreshOptions) {
  const [isEnabled, setIsEnabled] = useState(enabled);
  const [currentInterval, setCurrentInterval] = useState(interval);
  const intervalRef = useRef<number | null>(null);

  const start = useCallback(() => {
    setIsEnabled(true);
  }, []);

  const stop = useCallback(() => {
    setIsEnabled(false);
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const toggle = useCallback(() => {
    if (isEnabled) {
      stop();
    } else {
      start();
    }
  }, [isEnabled, start, stop]);

  const updateInterval = useCallback((newInterval: number) => {
    setCurrentInterval(newInterval);
  }, []);

  useEffect(() => {
    if (isEnabled) {
      intervalRef.current = window.setInterval(() => {
        void onRefresh();
      }, currentInterval);

      return () => {
        if (intervalRef.current !== null) {
          clearInterval(intervalRef.current);
        }
      };
    }
  }, [isEnabled, currentInterval, onRefresh]);

  return {
    isEnabled,
    currentInterval,
    start,
    stop,
    toggle,
    updateInterval,
  };
}

