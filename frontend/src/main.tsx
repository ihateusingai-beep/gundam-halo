import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router";

import App from "./App";
// Side-effect imports: register console-debug globals on `window` so they
// survive Vite tree-shaking. These are tiny and gated by `typeof window`.
import "./services/halo-live2d-bridge";
import "./services/halo-tray-controls";
import "./services/halo-voice-ws";
import "./services/halo-watchdog-events";
import "./styles/gundam.css";
import "./index.css";

// Set default theme BEFORE React renders to avoid flash
const defaultTheme =
  localStorage.getItem("gundam-halo-theme") || "gundam-ntd";
document.documentElement.setAttribute("data-theme", defaultTheme);

const defaultBg = localStorage.getItem("gundam-halo-bg");
if (defaultBg && defaultBg !== "none") {
  document.documentElement.setAttribute("data-bg", defaultBg);
}

// Load Live2D Cubism Core before rendering the app
const loadLive2DCore = () =>
  new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "/libs/live2dcubismcore.min.js";
    script.onload = () => {
      console.log("[Halo] Live2D Cubism Core loaded successfully.");
      resolve();
    };
    script.onerror = (error) => {
      console.error("[Halo] Failed to load Live2D Cubism Core:", error);
      reject(error);
    };
    document.head.appendChild(script);
  });

loadLive2DCore()
  .then(() => {
    ReactDOM.createRoot(document.getElementById("root")!).render(
      <React.StrictMode>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </React.StrictMode>
    );
  })
  .catch((error) => {
    console.error("[Halo] Application failed to start:", error);
    const rootElement = document.getElementById("root");
    if (rootElement) {
      rootElement.innerHTML =
        "Error loading Live2D core. Please check the console for details.";
    }
  });