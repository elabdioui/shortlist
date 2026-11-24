// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NextIntlClientProvider } from "next-intl";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import frMessages from "@/messages/fr.json";
import enMessages from "@/messages/en.json";

export type AppLocale = "fr" | "en";
export type AppTheme = "light" | "dark";

const MESSAGES: Record<AppLocale, typeof frMessages> = {
  fr: frMessages,
  en: enMessages,
};

interface AppPreferencesContextValue {
  locale: AppLocale;
  setLocale: (locale: AppLocale) => void;
  theme: AppTheme;
  toggleTheme: () => void;
}

const AppPreferencesContext = createContext<AppPreferencesContextValue>({
  locale: "fr",
  setLocale: () => {},
  theme: "light",
  toggleTheme: () => {},
});

export function useAppPreferences(): AppPreferencesContextValue {
  return useContext(AppPreferencesContext);
}

export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 10_000,
            retry: (failureCount, error) => {
              if (
                typeof error === "object" &&
                error !== null &&
                "status" in error &&
                ((error as { status: number }).status === 401 ||
                  (error as { status: number }).status === 403 ||
                  (error as { status: number }).status === 404)
              ) {
                return false;
              }
              return failureCount < 1;
            },
          },
        },
      })
  );

  const [locale, setLocaleState] = useState<AppLocale>("fr");
  const [theme, setThemeState] = useState<AppTheme>("light");

  useEffect(() => {
    const savedLocale = window.localStorage.getItem("shortlist_locale");
    if (savedLocale === "fr" || savedLocale === "en") {
      setLocaleState(savedLocale);
      document.documentElement.lang = savedLocale;
    }
    const savedTheme = window.localStorage.getItem("shortlist_theme");
    if (savedTheme === "dark" || savedTheme === "light") {
      setThemeState(savedTheme);
      document.documentElement.classList.toggle("dark", savedTheme === "dark");
    } else if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
      setThemeState("dark");
      document.documentElement.classList.add("dark");
    }
  }, []);

  const setLocale = useCallback((nextLocale: AppLocale) => {
    setLocaleState(nextLocale);
    window.localStorage.setItem("shortlist_locale", nextLocale);
    document.documentElement.lang = nextLocale;
  }, []);

  const toggleTheme = useCallback(() => {
    setThemeState((prev) => {
      const next: AppTheme = prev === "light" ? "dark" : "light";
      window.localStorage.setItem("shortlist_theme", next);
      document.documentElement.classList.toggle("dark", next === "dark");
      return next;
    });
  }, []);

  const prefValue = useMemo(
    () => ({ locale, setLocale, theme, toggleTheme }),
    [locale, setLocale, theme, toggleTheme]
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AppPreferencesContext.Provider value={prefValue}>
        <NextIntlClientProvider locale={locale} messages={MESSAGES[locale]} timeZone="UTC">
          {children}
        </NextIntlClientProvider>
      </AppPreferencesContext.Provider>
    </QueryClientProvider>
  );
}
