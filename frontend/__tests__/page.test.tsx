import React from "react";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api/generated", () => ({
  useScoresQuery: () => ({
    data: [
      { coin: "btc", score: 0.92 },
      { coin: "eth", score: 0.88 },
      { coin: "sol", score: 0.81 },
    ],
    isFetching: false,
    refetch: vi.fn(),
  }),
}));

import Home from "../../app/page";

describe("Home page", () => {
  it("renders the top 3 scores", () => {
    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <Home />
      </QueryClientProvider>
    );

    expect(screen.getByText(/Tokenlysis Dashboard/)).toBeInTheDocument();
    expect(screen.getByText("BTC")).toBeInTheDocument();
    expect(screen.getByText("ETH")).toBeInTheDocument();
  });
});
