import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Single-origin dev server.
//
// The browser talks only to this server; /api is proxied to the FastAPI
// container over the compose network. That keeps the frontend and the API on
// one origin, which means no CORS preflight at all — previously the API base
// was hardcoded to http://localhost:8000, so the moment the UI was served from
// anywhere other than the developer's own machine (a tunnel, another laptop,
// a phone on the LAN) every request pointed at the *viewer's* localhost and
// the app failed with "Unable to connect to the server".
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true, // listen on 0.0.0.0 so the container port is reachable
    watch: { usePolling: true, interval: 300 },
    allowedHosts: true,

    proxy: {
      "/api": {
        // Service name on the compose network. Falls back to localhost for a
        // bare `npm run dev` outside Docker.
        target: process.env.VITE_PROXY_TARGET || "http://api:8000",
        changeOrigin: true,
        // The API mounts its routes at the root (/auth/login, /cases), so the
        // /api marker is stripped before forwarding.
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      // NOTE: do not add bare "/cases", "/reports" or "/auth" entries here.
      //
      // They were added once and had to be removed: "/cases", "/cases/:id",
      // "/cases/:id/documents/:docId", "/cases/:id/charge-sheet" and
      // "/reports" are all React Router routes, so proxying those prefixes
      // hands the SPA's own URLs to the API instead of serving index.html.
      // Loading or refreshing any of those five pages returned 502 Bad
      // Gateway and a blank screen — including the document viewer, where
      // the redaction demo happens. The target compounded it: inside the web
      // container "localhost:8000" is the web container itself, not the API.
      //
      // Nothing needs them. Every API call goes through API_BASE = "/api"
      // (web/src/api/client.js), which the single rule above already covers.
    },
  },
  build: {
    sourcemap: false
  },
  test: {
    environment: "jsdom",
    globals: true
  }
});
