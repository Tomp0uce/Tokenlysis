"use client";

import React, { useMemo } from "react";
import { Loader2, TrendingUp } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";

import { Button } from "../frontend/components/ui/button";
import { useScoresQuery } from "../frontend/lib/api/generated";

const filtersSchema = z.object({
  theme: z.string().min(1, "Choose a theme").default("liquidity"),
});

type FiltersForm = z.infer<typeof filtersSchema>;

export default function Home() {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FiltersForm>({
    resolver: zodResolver(filtersSchema),
    defaultValues: { theme: "liquidity" },
  });

  const { data, isFetching, refetch } = useScoresQuery({ theme: "liquidity" });

  const top3 = useMemo(() => {
    return (data ?? []).slice(0, 3);
  }, [data]);

  const onSubmit = () => {
    void refetch();
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-8 p-10">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Tokenlysis Dashboard</h1>
          <p className="text-slate-300">FastAPI + Next.js stack with live scoring.</p>
        </div>
        <TrendingUp className="h-10 w-10 text-sky-400" />
      </header>

      <section>
        <form onSubmit={handleSubmit(onSubmit)} className="flex items-end gap-4">
          <label className="flex flex-col text-sm">
            Theme
            <select
              className="rounded border border-slate-600 bg-slate-800 px-3 py-2"
              {...register("theme")}
            >
              <option value="liquidity">Liquidity</option>
              <option value="technology">Technology</option>
              <option value="community">Community</option>
            </select>
            {errors.theme && <span className="text-xs text-red-400">{errors.theme.message}</span>}
          </label>

          <Button type="submit" disabled={isFetching}>
            {isFetching ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" /> Refreshing
              </span>
            ) : (
              "Update"
            )}
          </Button>
        </form>
      </section>

      <section>
        <h2 className="mb-3 text-xl font-semibold">Top 3</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {top3.map((score) => (
            <div key={score.coin} className="rounded-lg border border-slate-700 bg-slate-900 p-4">
              <p className="text-sm text-slate-400">{score.coin.toUpperCase()}</p>
              <p className="text-2xl font-bold">{Math.round(score.score * 100)}%</p>
            </div>
          ))}
          {top3.length === 0 && <p>No scores available.</p>}
        </div>
      </section>
    </main>
  );
}
