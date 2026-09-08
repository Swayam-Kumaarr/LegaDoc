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
      "/reports": {
        target: process.env.VITE_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
      "/auth": {
        target: process.env.VITE_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
      "/cases": {
        target: process.env.VITE_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    sourcemap: false
  }
});
