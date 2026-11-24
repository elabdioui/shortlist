// SPDX-License-Identifier: AGPL-3.0-or-later

import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import type { ReactNode } from "react";
import { AppProviders } from "@/components/providers/AppProviders";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
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
      className={`${inter.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <body className="min-h-screen bg-[var(--background)] font-sans text-[var(--foreground)] antialiased">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
