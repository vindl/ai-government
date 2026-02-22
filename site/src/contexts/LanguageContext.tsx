import { createContext, useContext, useState, useEffect, type ReactNode } from "react";

type Lang = "me" | "en";

interface LanguageContextType {
  lang: Lang;
  setLang: (lang: Lang) => void;
}

const LanguageContext = createContext<LanguageContextType>({
  lang: "me",
  setLang: () => {},
});

const STORAGE_KEY = "aigov-lang";

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    // 1. URL ?lang= parameter takes priority
    try {
      const params = new URLSearchParams(window.location.search);
      const urlLang = params.get("lang");
      if (urlLang === "en" || urlLang === "me") {
        localStorage.setItem(STORAGE_KEY, urlLang);
        return urlLang;
      }
    } catch {
      // SSR or URLSearchParams unavailable
    }
    // 2. localStorage
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "en" || stored === "me") return stored;
    } catch {
      // SSR or localStorage unavailable
    }
    // 3. Default
    return "me";
  });

  // Strip ?lang= from URL bar after applying it (keeps URLs clean during navigation)
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.has("lang")) {
        params.delete("lang");
        const newSearch = params.toString();
        const newUrl =
          window.location.pathname +
          (newSearch ? `?${newSearch}` : "") +
          window.location.hash;
        window.history.replaceState(null, "", newUrl);
      }
    } catch {
      // ignore
    }
  }, []);

  const setLang = (newLang: Lang) => {
    setLangState(newLang);
    try {
      localStorage.setItem(STORAGE_KEY, newLang);
    } catch {
      // ignore
    }
  };

  return (
    <LanguageContext.Provider value={{ lang, setLang }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  return useContext(LanguageContext);
}
