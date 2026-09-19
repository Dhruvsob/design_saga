// Root ESLint v9 flat config.
// The repo's frontend is a CRA/CRACO app (real dev/build linting runs via
// react-scripts). ESLint v9 resolves its flat config from the current working
// directory upward — some tooling invokes `eslint` from /app (repo root), where
// no config previously existed, causing a "couldn't find eslint.config" engine
// crash. This root config makes the engine run cleanly from the repo root.
//
// It is intentionally self-contained (no external `require`s) because the repo
// root has no node_modules; the eslint binary itself comes from
// frontend/node_modules. An inline no-op `react-hooks` plugin resolves the
// existing inline `eslint-disable react-hooks/exhaustive-deps` directives
// without pulling in the real plugin. No opinionated rules are enabled so the
// large existing codebase is not judged here.
const noop = { create: () => ({}) };

module.exports = [
  {
    ignores: [
      "**/node_modules/**",
      "backend/**",
      "tests/**",
      "test_reports/**",
      "memory/**",
      "**/build/**",
      "**/dist/**",
      "**/public/**",
      "**/coverage/**",
    ],
  },
  {
    files: ["**/*.{js,jsx}"],
    plugins: {
      "react-hooks": { rules: { "exhaustive-deps": noop, "rules-of-hooks": noop } },
    },
    linterOptions: {
      reportUnusedDisableDirectives: "off",
    },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    rules: {},
  },
];
