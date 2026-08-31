import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppShell } from "@/components/app-shell";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: {
    default: "sl3dge | Financial evidence workspace",
    template: "%s | sl3dge",
  },
  description: "Review financial controls, exceptions, and source-linked evidence.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html className="h-full antialiased" lang="en">
      <body className="min-h-full">
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
