"use client";
import { useEffect, useState } from "react";

export function useResource<T>(path: string | null, delay = 0) {
  const [retry, setRetry] = useState(0);
  const [state, setState] = useState<{
    key: string;
    data?: T;
    error?: string;
  } | null>(null);
  const key = `${path}:${retry}`;
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(`/api/football/${path}`, {
          signal: controller.signal,
          cache: "no-store",
        });
        const body = await response.json();
        if (!response.ok) throw new Error(body.error ?? "Unable to load data.");
        if (!controller.signal.aborted) setState({ key, data: body as T });
      } catch (error) {
        if (!controller.signal.aborted)
          setState({
            key,
            error:
              error instanceof Error ? error.message : "Unable to load data.",
          });
      }
    }, delay);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [path, key, delay]);
  const current = path && state?.key === key ? state : null;
  return {
    data: current?.data,
    error: current?.error,
    loading: Boolean(path && !current),
    retry: () => setRetry((value) => value + 1),
  };
}
