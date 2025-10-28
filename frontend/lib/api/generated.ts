import axios from "axios";
import { useQuery, UseQueryOptions } from "@tanstack/react-query";

export interface ScoreResponse {
  coin: string;
  score: number;
}

export interface ScoresParams {
  theme?: string;
}

export const client = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
});

export const getScores = async (params?: ScoresParams): Promise<ScoreResponse[]> => {
  const response = await client.get<ScoreResponse[]>("/api/scores", { params });
  return response.data;
};

export const useScoresQuery = (
  params?: ScoresParams,
  options?: UseQueryOptions<ScoreResponse[], Error>
) => {
  return useQuery<ScoreResponse[], Error>({
    queryKey: ["scores", params],
    queryFn: () => getScores(params),
    staleTime: 10_000,
    ...options,
  });
};
