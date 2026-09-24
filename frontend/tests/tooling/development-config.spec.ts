import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { afterEach, describe, expect, it, vi } from 'vitest'

const REPOSITORY_ROOT = join(import.meta.dirname, '../../..')

afterEach(() => {
  vi.unstubAllEnvs()
  vi.resetModules()
})

describe('development API proxy', () => {
  it.each([
    [undefined, 'http://localhost:8000'],
    ['', 'http://localhost:8000'],
    ['http://api:8000', 'http://api:8000'],
  ])('resolves server-only target %s to %s', async (configured, expected) => {
    vi.stubEnv('GENDERTAGGER_DEV_API_TARGET', configured)
    vi.resetModules()

    const { default: config } = await import('../../vite.config')

    expect(config.server?.proxy?.['/api/v1']).toBe(expected)
    // No client-side API origin is introduced: browser requests remain same-origin.
    expect(config.define).toBeUndefined()
    expect(config.envPrefix).toBeUndefined()
  })
})

describe('development deployment policy', () => {
  it('keeps the Vite image distinct from the production image', () => {
    const production = readFileSync(join(REPOSITORY_ROOT, 'compose.yaml'), 'utf-8')
    const development = readFileSync(join(REPOSITORY_ROOT, 'compose.dev.yaml'), 'utf-8')
    // Inspect only the frontend service without adding a YAML parser dependency.
    const productionFrontend = production.split(/^ {2}frontend:\s*$/m)[1]?.split(/^ {2}\S/m)[0]
    const developmentFrontend = development.split(/^ {2}frontend:\s*$/m)[1]?.split(/^ {2}\S/m)[0]

    expect(productionFrontend).toContain('target: production')
    expect(productionFrontend).toContain('frontend:${TAG:-latest}')
    expect(developmentFrontend).toContain('target: development')
    expect(developmentFrontend).toContain('frontend-dev:${TAG:-latest}')
    expect(developmentFrontend).toContain('GENDERTAGGER_DEV_API_TARGET: http://api:8000')
    expect(developmentFrontend).toContain('./frontend:/app')
    expect(developmentFrontend).toContain('- /app/node_modules')
  })

  it('keeps the development server on the gateway upstream port', () => {
    const dockerfile = readFileSync(
      join(REPOSITORY_ROOT, 'deploy/docker/frontend.Dockerfile'),
      'utf-8',
    )
    const development = dockerfile.split(' AS development\n')[1]?.split(/^FROM /m)[0]
    const gateway = readFileSync(join(REPOSITORY_ROOT, 'deploy/proxy/nginx.conf'), 'utf-8')

    expect(development).toContain('"--host", "0.0.0.0", "--port", "80", "--strictPort"')
    expect(gateway).toMatch(/upstream frontend_server\s*\{\s*server frontend:80;/)
  })

  it('forwards WebSocket upgrades only through the frontend route', () => {
    const gateway = readFileSync(join(REPOSITORY_ROOT, 'deploy/proxy/nginx.conf'), 'utf-8')
    const frontendRoute = gateway.match(/location \/\s*\{([^}]+)\}/)?.[1]

    expect(gateway).toMatch(/map \$http_upgrade \$frontend_connection\s*\{\s*default upgrade;/)
    expect(frontendRoute).toContain('proxy_pass http://frontend_server;')
    expect(frontendRoute).toContain('proxy_http_version 1.1;')
    expect(frontendRoute).toContain('proxy_set_header Upgrade $http_upgrade;')
    expect(frontendRoute).toContain('proxy_set_header Connection $frontend_connection;')
    expect(gateway.match(/proxy_set_header Upgrade /g)).toHaveLength(1)
  })
})
