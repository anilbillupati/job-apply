import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const target = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    host: true,
    proxy: {
      "/api": { target, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") },
    },
  },
});
