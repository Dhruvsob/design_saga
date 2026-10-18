// Minimal ESLint v9 flat config.
// Keep linting intentionally conservative while the legacy UI is modernized.
// It registers the react-hooks plugin only so existing inline
// `eslint-disable react-hooks/exhaustive-deps` directives resolve, but keeps rules off
// to avoid altering behavior or failing on pre-existing choices in the large codebase.
const globals = require("globals");
const reactHooks = require("eslint-plugin-react-hooks");

module.exports = [
  {
    ignores: [
      "build/**",
      "dist/**",
      "node_modules/**",
      "public/**",
      "coverage/**",
    ],
  },
  {
    files: ["**/*.{js,jsx}"],
    plugins: {
      "react-hooks": reactHooks,
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
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.jest,
      },
    },
    rules: {
      "react-hooks/rules-of-hooks": "off",
      "react-hooks/exhaustive-deps": "off",
    },
  },
];
