import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "./styles.css";
import { keycloak } from "./keycloak";

keycloak
  .init({ onLoad: "login-required", checkLoginIframe: false })
  .then((auth) => {
    if (!auth) return; // mid-redirect, do nothing
    ReactDOM.createRoot(document.getElementById("root")!).render(
      <React.StrictMode>
        <App />
      </React.StrictMode>,
    );
    setInterval(() => keycloak.updateToken(30), 60_000);
  })
  .catch(() => {
    document.getElementById("root")!.innerHTML =
      "<p style='padding:2rem;color:red'>Authentication error — check console.</p>";
  });
