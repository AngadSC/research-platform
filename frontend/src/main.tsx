import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { App } from "./App";
import { applyTheme, getStoredTheme } from "./lib/theme";

applyTheme(getStoredTheme());

// A deploy renames the built chunks, so a tab opened before it fails to load a lazy page.
// Reload once to pick up the new build (the flag stops a reload loop if a chunk is truly missing).
window.addEventListener("vite:preloadError", (event) => {
  try {
    if (sessionStorage.getItem("reloaded-for-deploy")) return;
    sessionStorage.setItem("reloaded-for-deploy", "1");
  } catch {
    return;
  }
  event.preventDefault();
  window.location.reload();
});
window.addEventListener("load", () => {
  try {
    setTimeout(() => sessionStorage.removeItem("reloaded-for-deploy"), 10_000);
  } catch {
    /* storage blocked */
  }
});

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Root element #root not found");

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
