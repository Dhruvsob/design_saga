import { defineConfig, transformWithOxc } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const sourceJsAsJsx = {
  name: "source-js-as-jsx",
  enforce: "pre",
  async transform(code, id) {
    if (!/[\\/]src[\\/].*\.js$/.test(id)) return null;
    return transformWithOxc(code, id, { lang: "jsx", sourcemap: true });
  },
};

export default defineConfig({
  plugins: [sourceJsAsJsx, react({ include: /\.[jt]sx?$/ })],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    sourcemap: false,
  },
});
