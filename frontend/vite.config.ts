import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// Same-origin topology (docs/17-frontend-integration.md): the browser only ever talks to its own
// origin. In development the Vite server stands in for the reverse proxy.
const API_DEVELOPMENT_TARGET = 'http://localhost:8000'

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
