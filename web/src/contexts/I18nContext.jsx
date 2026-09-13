import React, { createContext, useContext, useState } from "react";
import { translations, SUPPORTED_LANGUAGES } from "../i18n/translations";

const I18nContext = createContext();

export function I18nProvider({ children }) {
  const [language, setLanguageState] = useState(() => {
    return localStorage.getItem("preferred_language") || "en";
  });

  const setLanguage = (langCode) => {
    if (translations[langCode]) {
      setLanguageState(langCode);
      localStorage.setItem("preferred_language", langCode);
    }
  };

  const t = (key, fallback = "") => {
    const currentDict = translations[language] || translations["en"];
    if (currentDict && currentDict[key]) {
      return currentDict[key];
    }
    const englishDict = translations["en"];
    if (englishDict && englishDict[key]) {
      return englishDict[key];
    }
    return fallback || key;
  };

  return (
    <I18nContext.Provider
      value={{
        language,
        setLanguage,
        t,
        supportedLanguages: SUPPORTED_LANGUAGES,
      }}
    >
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used within an I18nProvider");
  }
  return context;
}
