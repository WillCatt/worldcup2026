import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// Build to a self-contained static bundle under the hub's pieces/ dir so the
// 03 tile links straight to it. base:'./' keeps every asset path relative, so
// the bundle works at any nested URL (here, or once ported to williamcatt.dev).
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: resolve(__dirname, "../site/pieces/travel"),
    emptyOutDir: true,
  },
});
