import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// See SYSTEM_DESIGN.md, Environments — API_BASE points at the FastAPI service
// (http://localhost:8000 locally via docker compose).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Docker Desktop on Windows often doesn't propagate native filesystem
    // change events through a bind mount (./web/src -> /app/src in
    // docker-compose.yml), so Vite's default watcher silently never sees
    // edits made from the host side — polling actually checks file
    // contents on an interval instead of waiting for an event that never
    // arrives. Harmless overhead on Linux/Mac where events do propagate.
    watch: { usePolling: true, interval: 300 },
  },
  build: {
    sourcemap: false
  }
});
