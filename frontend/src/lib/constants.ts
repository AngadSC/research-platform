export const APP_NAME = "labbenchos";

/** Name of the shortcut modifier on this machine, for hints. */
export const MOD_KEY =
  typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform) ? "Cmd" : "Ctrl";
/** Window event that opens the command palette (the header search button fires it). */
export const OPEN_SEARCH_EVENT = "open-search";
/** Window event that starts the guided tour (components/layout/Tutorial). */
export const OPEN_TUTORIAL_EVENT = "open-tutorial";
/** Where the Help page's feedback link goes. Swap it for a form or mailto: if you get one. */
export const FEEDBACK_URL = "https://github.com/AngadSC/research-platform/issues/new";

export const OPEN_QUICK_CAPTURE_EVENT = "open-quick-capture";
