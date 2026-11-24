// SPDX-License-Identifier: AGPL-3.0-or-later

import type { Metadata } from "next";
import { IBM_Plex_Sans, JetBrains_Mono } from "next/font/google";
import type { ReactNode } from "react";
import { AppProviders } from "@/components/providers/AppProviders";
import "./globals.css";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-sans",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Shortlist — Tri de CV assisté par IA",
  description:
    "Outil open source et auto-hébergé pour classer des CV avec des preuves vérifiables.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html
      lang="fr"
      className={`${plexSans.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <body className="min-h-screen bg-[var(--background)] font-sans text-[var(--foreground)] antialiased">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
