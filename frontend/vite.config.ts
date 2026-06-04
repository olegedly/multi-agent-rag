import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import solidPlugin from "vite-plugin-solid";
import devtools from "solid-devtools/vite";

export default defineConfig({
  plugins: [devtools(), solidPlugin(), tailwindcss()],
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000", // Your FastAPI server address
        changeOrigin: true,
      },
    },
  },
  build: {
    target: "esnext",
  },
});
