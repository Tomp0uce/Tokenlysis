import { defineConfig } from "orval";

export default defineConfig({
  tokenlysis: {
    input: "http://localhost:8000/openapi.json",
    output: {
      target: "frontend/lib/api/generated.ts",
      client: "react-query",
      mode: "single", 
      prettier: false,
    },
  },
});
