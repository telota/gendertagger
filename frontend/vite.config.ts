import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// Same-origin topology (docs/17-frontend-integration.md): the browser only ever talks to its own
// origin. The gateway routes API traffic in Docker; Vite also proxies it for direct dev-server
// access. This server-only setting points at the API container, or the host API by default.
const API_DEVELOPMENT_TARGET = process.env.GENDERTAGGER_DEV_API_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      '/api/v1': API_DEVELOPMENT_TARGET,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.spec.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,vue}'],
      exclude: ['src/**/*.d.ts', 'src/main.ts'],
      reporter: ['text', 'cobertura'],
      // Decision D11: the 80 % branch-coverage floor applies from the first milestone.
      thresholds: {
        branches: 80,
      },
    },
  },
})
