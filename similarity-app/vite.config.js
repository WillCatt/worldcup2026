import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// Self-contained static bundle under the hub's pieces/ dir (the 05 tile links
// here). base:'./' keeps asset paths relative so it works at any nested URL.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: resolve(__dirname, "../site/pieces/similarity"),
    emptyOutDir: true,
  },
});
