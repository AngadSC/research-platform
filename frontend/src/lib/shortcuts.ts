import { MOD_KEY } from "@/lib/constants";

/** Every keyboard shortcut the app really has: the Help page and the "?" cheat sheet read this. */
export const SHORTCUTS = [
  [`${MOD_KEY} K`, "Search, or jump to any page"],
  [`${MOD_KEY} G`, "Add a task"],
  [`${MOD_KEY} S`, "Save the document you are editing"],
  ["/", "In a document, open the list of things to add"],
  ["Up, Down, Enter", "Move through the search results and open one"],
  [`${MOD_KEY} .`, "Open or close the assistant"],
  ["?", "Show this list"],
  ["Esc", "Close a dialog, menu or the side menu"],
] as const;
