// SPDX-License-Identifier: AGPL-3.0-or-later

import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppProviders } from "@/components/providers/AppProviders";
import "./globals.css";

export const metadata: Metadata = {
  title: "Shortlist — Tri de CV assisté par IA",
  description:
    "Outil open source et auto-hébergé pour classer des CV avec des preuves vérifiables.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="fr" suppressHydrationWarning>
      <body className="min-h-screen bg-[var(--background)] text-[var(--foreground)] antialiased">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
