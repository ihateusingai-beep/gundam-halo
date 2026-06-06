import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router";

import App from "./App";
import "./styles/gundam.css";
import "./index.css";

// Set default theme BEFORE React renders to avoid flash
// (Real theme is loaded from user config via /api/config or localStorage)
const defaultTheme = localStorage.getItem("gundam-halo-theme") || "gundam-ntd";
document.documentElement.setAttribute("data-theme", defaultTheme);

// Same for background (data-bg attribute, "none" = pure hex grid)
const defaultBg = localStorage.getItem("gundam-halo-bg");
if (defaultBg && defaultBg !== "none") {
  document.documentElement.setAttribute("data-bg", defaultBg);
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
