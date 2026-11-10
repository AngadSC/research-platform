export const APP_NAME = "labbenchos";

/** Name of the shortcut modifier on this machine, for hints. */
export const MOD_KEY =
  typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform) ? "Cmd" : "Ctrl";
/** Window event that opens the command palette (the header search button fires it). */
export const OPEN_SEARCH_EVENT = "open-search";
