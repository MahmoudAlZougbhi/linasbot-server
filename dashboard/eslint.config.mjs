import js from "@eslint/js";
import globals from "globals";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default [
  { ignores: ["build", "dist", "node_modules"] },
  js.configs.recommended,
  {
    files: ["**/*.mjs", "**/*.cjs"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: { ...globals.node },
    },
  },
  {
    files: ["**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.es2021,
      },
    },
    settings: {
      react: { version: "detect" },
    },
    plugins: {
      react,
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs["jsx-runtime"].rules,
      // Only the two classic hook rules (matches CRA's former
      // react-app/react-app/jest preset). eslint-plugin-react-hooks@7's
      // "recommended" config adds many new React-Compiler-style rules
      // (immutability, set-state-in-effect, purity, etc.) that would flag
      // a large amount of pre-existing, working code unrelated to this
      // build-tooling migration.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "react/prop-types": "off",
      "react-refresh/only-export-components": "off",
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
      // Downgraded to match the leniency of CRA's former react-app/react-app/jest
      // preset, which did not fail the build on these stylistic issues. They
      // flag pre-existing patterns unrelated to this build-tooling migration.
      "react/no-unescaped-entities": "warn",
      "no-useless-catch": "warn",
      "no-case-declarations": "warn",
      "no-empty": "warn",
    },
  },
  {
    files: ["**/*.test.{js,jsx}", "src/setupTests.js"],
    languageOptions: {
      globals: {
        ...globals.node,
        ...globals.browser,
        vi: "readonly",
        describe: "readonly",
        it: "readonly",
        test: "readonly",
        expect: "readonly",
        beforeEach: "readonly",
        afterEach: "readonly",
      },
    },
  },
];
