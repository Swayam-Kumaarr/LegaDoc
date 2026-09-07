import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// See SYSTEM_DESIGN.md, Environments — API_BASE points at the FastAPI service
// (http://localhost:8000 locally via docker compose).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/reports': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
      '/cases': 'http://localhost:8000',
    }
  },
  build: {
    sourcemap: false
  }
});
