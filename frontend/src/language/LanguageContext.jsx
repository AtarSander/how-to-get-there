import { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  LOCALE_STORAGE_KEY,
  SUPPORTED_LOCALES,
  translations,
} from "./translations";

const LanguageContext = createContext(null);

function readStoredLocale() {
  const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
  return SUPPORTED_LOCALES.includes(stored) ? stored : "pl";
}

function resolveMessage(messages, key) {
  return key.split(".").reduce((value, part) => value?.[part], messages);
}

function formatMessage(template, params) {
  if (!params) {
    return template;
  }

  return Object.entries(params).reduce(
    (result, [name, value]) => result.replaceAll(`{{${name}}}`, String(value)),
    template,
  );
}

export function LanguageProvider({ children }) {
  const [locale, setLocaleState] = useState(readStoredLocale);

  useEffect(() => {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale);
    document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo(() => {
    const messages = translations[locale] ?? translations.pl;

    function t(key, params) {
      const message = resolveMessage(messages, key);
      if (typeof message !== "string") {
        return key;
      }
      return formatMessage(message, params);
    }

    function setLocale(nextLocale) {
      if (SUPPORTED_LOCALES.includes(nextLocale)) {
        setLocaleState(nextLocale);
      }
    }

    return { locale, setLocale, t };
  }, [locale]);

  return (
    <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
  );
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useLanguage must be used within LanguageProvider");
  }
  return context;
}
