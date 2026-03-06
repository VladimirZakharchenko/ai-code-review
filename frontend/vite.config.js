import { svelte } from "@sveltejs/vite-plugin-svelte";

/** @type {import('vite').UserConfig} */
const config = {
  plugins: [svelte()],
  server: {
    port: 4173,
    host: "0.0.0.0"
  }
};

export default config;

