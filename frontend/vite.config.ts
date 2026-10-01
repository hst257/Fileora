import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { copyFileSync, mkdirSync } from "node:fs";

export default defineConfig({
  plugins: [
    react(),
    {
      name: "local-api-documentation",
      apply: "build",
      closeBundle() {
        const destination = new URL("./dist/api-docs/", import.meta.url);
        mkdirSync(destination, { recursive: true });
        for (const file of [
          "swagger-ui.css",
          "swagger-ui-bundle.js",
          "swagger-ui-bundle.js.LICENSE.txt",
        ]) {
          copyFileSync(
            new URL(`./node_modules/swagger-ui-dist/${file}`, import.meta.url),
            new URL(file, destination),
          );
        }
      },
    },
  ],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        configure(proxy) {
          proxy.on("proxyReq", (req) => {
            req.removeHeader("origin");
          });
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    exclude: ["node_modules/**", "e2e/**"],
  },
});
