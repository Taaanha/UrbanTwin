import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";
import { defineConfig, type Plugin } from "vite";
import { viteStaticCopy } from "vite-plugin-static-copy";

// Cesium loads its workers, widget CSS and assets at runtime from CESIUM_BASE_URL, so copy them into the build.
const cesiumSource = "node_modules/cesium/Build/Cesium";

// In `vite dev` the static-copy plugin does not serve these files, so serve Cesium's build folder directly.
const serveCesiumInDev: Plugin = {
  name: "serve-cesium-in-dev",
  apply: "serve",
  configureServer(server) {
    const root = path.resolve(cesiumSource);
    server.middlewares.use("/cesium", (req, res, next) => {
      const file = path.join(root, decodeURIComponent((req.url ?? "/").split("?")[0]));
      if (!file.startsWith(root) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return next();
      const types: Record<string, string> = { ".js": "text/javascript", ".json": "application/json", ".css": "text/css", ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".wasm": "application/wasm" };
      res.setHeader("Content-Type", types[path.extname(file)] ?? "application/octet-stream");
      fs.createReadStream(file).pipe(res);
    });
  },
};

export default defineConfig({
  define: { CESIUM_BASE_URL: JSON.stringify("/cesium") },
  plugins: [
    serveCesiumInDev,
    react(),
    tailwindcss(),
    viteStaticCopy({
      targets: [
        { src: `${cesiumSource}/Workers`, dest: "cesium" },
        { src: `${cesiumSource}/ThirdParty`, dest: "cesium" },
        { src: `${cesiumSource}/Assets`, dest: "cesium" },
        { src: `${cesiumSource}/Widgets`, dest: "cesium" },
      ],
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
