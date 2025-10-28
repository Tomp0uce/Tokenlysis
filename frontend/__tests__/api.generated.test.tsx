import React, { type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";

import { client, getScores, useScoresQuery } from "../lib/api/generated";

describe("orval generated client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches scores with axios", async () => {
    vi.spyOn(client, "get").mockResolvedValue({ data: [{ coin: "btc", score: 0.9 }] });

    const result = await getScores();
    expect(result[0].coin).toBe("btc");
  });

  it("exposes a TanStack Query hook", async () => {
    const queryClient = new QueryClient();
    vi.spyOn(client, "get").mockResolvedValue({ data: [{ coin: "eth", score: 0.8 }] });

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useScoresQuery(), { wrapper });

    const refetchResult = await result.current.refetch();
    expect(refetchResult.data?.[0].coin).toBe("eth");
  });
});
