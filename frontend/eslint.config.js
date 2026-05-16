import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    rules: {
      'no-unused-vars': ['error', {
        varsIgnorePattern: '^[A-Z_]',
        // Args starting with _ (convention) or a capital letter
        // (e.g. `icon: Icon` renamed during destructure to be usable
        // as a JSX component).
        argsIgnorePattern: '^(_|[A-Z])',
        // Array destructure: `[, Icon, tone]` — Icon used as a JSX
        // component is treated as unused without this pattern.
        destructuredArrayIgnorePattern: '^[A-Z_]',
        // Don't fail on unused caught errors — `catch (e) {}`,
        // `catch (refreshError) {}`, etc. are common patterns where
        // the error is intentionally discarded.
        caughtErrors: 'none',
      }],
      // Fast Refresh is a dev-only optimization. Context files that
      // export both a Provider and a hook are a common, legitimate
      // pattern; the rule flags them as a Fast Refresh limitation.
      'react-refresh/only-export-components': 'off',
      // Intentional empty catches are fine when the error genuinely
      // can be ignored (best-effort cleanups, etc.). The diff makes
      // the intent clear; we don't want a comment-noise tax for it.
      'no-empty': ['error', { allowEmptyCatch: true }],
      // `setState` inside `useEffect` for loading/data flags is a
      // common, intentional pattern in this codebase. The new
      // react-hooks rule flags it for cascading-render concerns;
      // downgrade to a warning until we refactor those effects.
      'react-hooks/set-state-in-effect': 'warn',
    },
  },
])
