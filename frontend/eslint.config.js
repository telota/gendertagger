import js from '@eslint/js'
import vueI18n from '@intlify/eslint-plugin-vue-i18n'
import pluginVue from 'eslint-plugin-vue'
import vueAccessibility from 'eslint-plugin-vuejs-accessibility'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  {
    // schema.d.ts is generated; the wireframe is a layout reference, not maintained source.
    ignores: [
      'dist/**',
      'coverage/**',
      'node_modules/**',
      'src/api/schema.d.ts',
      'gendertagger.html',
    ],
  },

  js.configs.recommended,
  ...tseslint.configs.strict,
  ...pluginVue.configs['flat/recommended'],
  ...vueAccessibility.configs['flat/recommended'],
  ...vueI18n.configs['flat/recommended'],

  {
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'module',
      globals: { ...globals.browser },
    },
    settings: {
      'vue-i18n': {
        localeDir: './src/locales/*.json',
        messageSyntaxVersion: '^11.0.0',
      },
    },
    rules: {
      // docs/26-frontend-coding-guidelines.md. Type-only imports are enforced by the compiler
      // (verbatimModuleSyntax), so no separate lint rule is needed.
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-non-null-assertion': 'error',
      'no-empty': ['error', { allowEmptyCatch: false }],

      'vue/block-order': ['error', { order: ['script', 'template', 'style'] }],
      'vue/block-lang': ['error', { script: { lang: 'ts' } }],
      'vue/component-api-style': ['error', ['script-setup']],
      'vue/define-props-declaration': ['error', 'type-based'],
      'vue/define-emits-declaration': ['error', 'type-literal'],
      'vue/multi-word-component-names': ['error', { ignores: ['App'] }],
      'vue/no-v-html': 'error',
      'vue/no-use-v-if-with-v-for': 'error',
      // docs/26: `v-for` needs a stable domain key, never the array index.
      'vue/no-restricted-syntax': [
        'error',
        {
          selector:
            "VAttribute[directive=true][key.argument.name='key'] > VExpressionContainer > Identifier[name=/^(index|idx|i)$/]",
          message: 'Use a stable domain key (tei_id or a resource id), not the array index.',
        },
      ],
      'vue/no-unused-refs': 'error',

      // Layout is owned by Prettier; these rules would fight it.
      'vue/singleline-html-element-content-newline': 'off',
      'vue/multiline-html-element-content-newline': 'off',
      'vue/max-attributes-per-line': 'off',
      'vue/first-attribute-linebreak': 'off',
      'vue/html-indent': 'off',
      'vue/html-closing-bracket-newline': 'off',

      // No user-facing string literal in a component; the key style is dot-separated camelCase.
      '@intlify/vue-i18n/no-raw-text': 'error',
      '@intlify/vue-i18n/no-missing-keys': 'error',
      '@intlify/vue-i18n/no-unused-keys': [
        'error',
        { extensions: ['.ts', '.vue'], enableFix: false },
      ],
      '@intlify/vue-i18n/key-format-style': ['error', 'camelCase', { splitByDots: true }],
    },
  },

  {
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
  },

  {
    // The theme bootstrap is a classic script, not a module.
    files: ['public/**/*.js'],
    languageOptions: { sourceType: 'script' },
  },

  {
    files: ['scripts/**/*.mjs', 'vite.config.ts', 'eslint.config.js'],
    languageOptions: { globals: { ...globals.node } },
  },

  {
    files: ['tests/**/*.ts'],
    rules: {
      '@typescript-eslint/no-non-null-assertion': 'off',
    },
  },
)
