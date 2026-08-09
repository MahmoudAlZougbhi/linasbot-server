import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Migrated from Create React App. Notes for maintainers:
// - `base: "./"` reproduces CRA's `homepage: "."` so the built index.html uses
//   relative asset URLs (works when FastAPI serves the SPA from arbitrary paths).
// - `build.outDir`/`assetsDir` are set to `build`/`static` so main.py's existing
//   `app.mount("/static", StaticFiles(directory=".../dashboard/build/static"))`
//   and `DASHBOARD_BUILD_PATH = ".../dashboard/build"` keep working unchanged.
// - `envPrefix` keeps `REACT_APP_*` (legacy) and `VITE_*` (new) vars readable via
//   `import.meta.env`. Existing source still reads `process.env.REACT_APP_*`
//   directly, so those specific keys are also inlined via `define` below —
//   this mirrors CRA's webpack DefinePlugin behavior without touching call sites.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), ["REACT_APP_", "VITE_"]);
  const processEnvDefine = {
    "process.env.REACT_APP_DEPLOY_VERSION": JSON.stringify(env.REACT_APP_DEPLOY_VERSION || "dev"),
    "process.env.REACT_APP_DEPLOY_COMMIT": JSON.stringify(env.REACT_APP_DEPLOY_COMMIT || "local"),
    ...Object.fromEntries(
      Object.entries(env).map(([key, value]) => [`process.env.${key}`, JSON.stringify(value)])
    ),
  };

  return {
    plugins: [
      react({
        include: "**/*.{js,jsx,ts,tsx}",
      }),
    ],
    envPrefix: ["REACT_APP_", "VITE_"],
    base: "./",
    define: processEnvDefine,
    server: {
      port: 3000,
      host: true,
      proxy: {
        // Matches former src/setupProxy.js (http-proxy-middleware) behavior.
        "/agent": {
          target: "https://boc-lb.com",
          changeOrigin: true,
          secure: false,
        },
        "/api": {
          target: "http://localhost:8003",
          changeOrigin: true,
        },
      },
    },
    preview: {
      port: 3000,
      host: true,
    },
    build: {
      outDir: "build",
      assetsDir: "static",
      sourcemap: true,
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: "./src/setupTests.js",
      css: true,
      include: ["src/**/*.test.{js,jsx,ts,tsx}"],
    },
  };
});
