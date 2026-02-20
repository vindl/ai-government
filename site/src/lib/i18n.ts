/**
 * Pick the right string based on current language.
 * Usage: t(lang, enValue, mneValue)
 */
export function t(lang: "me" | "en", en: string, mne: string): string {
  return lang === "en" ? en : mne;
}

/**
 * Pick from an array pair based on language.
 */
export function tList(lang: "me" | "en", en: string[], mne: string[]): string[] {
  return lang === "en" ? en : (mne.length > 0 ? mne : en);
}
