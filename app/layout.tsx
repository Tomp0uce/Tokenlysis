import "../frontend/styles/globals.css";
import type { Metadata } from "next";
import { ReactNode } from "react";

import { Providers } from "../frontend/components/providers";

export const metadata: Metadata = {
  title: "Tokenlysis Dashboard",
  description: "Crypto asset scoring on the FastAPI + Next.js stack",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
