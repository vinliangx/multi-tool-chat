import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  css: {
    postcss: "./postcss.config.js",
  },
  server: {
    port: 5173,
    proxy: {
      "/chat": "http://backend:8000",
      "/sessions": "http://backend:8000",
      "/health": "http://backend:8000",
      "/upload_url": "http://backend:8000",
      "/config": "http://backend:8000",
    },
  },
});
