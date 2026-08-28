"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

/** Single shared run-list query so the shell and every page read one cache entry. */
export function useRuns() {
  return useQuery({ queryKey: ["runs"], queryFn: api.runs });
}

/** Run-scoped list query that keeps the previous run's data visible while the next loads. */
export function useRunScopedQuery<T>(
  key: readonly unknown[],
  queryFn: () => Promise<T>,
  enabled: boolean,
) {
  return useQuery({
    queryKey: key,
    queryFn,
    enabled,
    placeholderData: keepPreviousData,
  });
}
