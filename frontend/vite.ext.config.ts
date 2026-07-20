import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { resolve } from "node:path";

// Separate build for the VS Code extension's lean UI (ext.html → dist-ext/).
// Keeps the extension bundle small and independent of the full web app.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    outDir: "dist-ext",
    emptyOutDir: true,
    rollupOptions: {
      input: resolve(__dirname, "ext.html"),
    },
  },
});
