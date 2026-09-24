// Smoke test of the built client behind the same-origin gateway, in a real Chrome over the DevTools
// Protocol (decision D13, M9 exit criterion): a deep link without a session goes to /login, signing
// in works with the secure cookie, the review deep link opens, a decision is made with the keyboard
// (key 2, then Enter), other screens load, and a hard reload on a deep link keeps the session.
//
//   docker compose -f compose.yaml up -d --build frontend gateway   # the production profile
//   node scripts/production-smoke.mjs
//
// It needs the development seed (backend/scripts/seed_frontend_development.py): it signs in as
// `frontend-reviewer` and appends ONE annotation to the first person of the contested queue. Never
// point it at a real deployment. Settings (environment): SMOKE_BASE (default http://localhost),
// SMOKE_USER / SMOKE_PASSWORD, CHROME_PATH, SMOKE_OUT (screenshot directory).
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const BASE = process.env.SMOKE_BASE ?? 'http://localhost'
const USER = process.env.SMOKE_USER ?? 'frontend-reviewer'
const PASSWORD = process.env.SMOKE_PASSWORD ?? 'development-only'
const OUT = process.env.SMOKE_OUT ?? path.join(os.tmpdir(), 'gendertagger-smoke')
const CHROME =
  process.env.CHROME_PATH ??
  (process.platform === 'win32'
    ? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
    : '/usr/bin/google-chrome')
const PORT = 9333

fs.mkdirSync(OUT, { recursive: true })
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'gt-chrome-'))
const chrome = spawn(
  CHROME,
  [
    '--headless=new',
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${profile}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--hide-scrollbars',
    'about:blank',
  ],
  { stdio: 'ignore' },
)

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const results = []
function check(name, ok, detail = '') {
  results.push(ok)
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  (' + detail + ')' : ''}`)
}

async function connect() {
  for (let i = 0; i < 60; i++) {
    try {
      const targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json()
      const page = targets.find((t) => t.type === 'page')
      if (page) return new WebSocket(page.webSocketDebuggerUrl)
    } catch {
      /* Chrome is not up yet */
    }
    await sleep(250)
  }
  throw new Error('Chrome did not start')
}

// Find the seeded run and aggregation through the API. The project's working aggregation
// (ADR-0035) is the seeded one; a run can have others, with different results.
async function discover() {
  const login = await fetch(`${BASE}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: USER, password: PASSWORD }),
  })
  if (!login.ok) throw new Error(`sign-in failed (${login.status})`)
  // The cookies are Secure; Node keeps none, so hand them back by hand.
  const cookie = login.headers
    .getSetCookie()
    .map((c) => c.split(';')[0])
    .join('; ')
  const get = async (p) => (await fetch(`${BASE}/api/v1${p}`, { headers: { cookie } })).json()
  const project = (await get('/projects')).items.find((p) => p.slug === 'frontend-demo')
  if (!project?.working_aggregation_execution_id) return null
  const aggregation = await get(`/aggregations/${project.working_aggregation_execution_id}`)
  const run = await get(`/runs/${aggregation.run_id}`)
  const evaluation = (await get(`/runs/${run.id}/evaluations`)).items.find(
    (e) => e.status === 'completed',
  )
  return {
    project: project.id,
    snapshot: run.dataset_snapshot_id,
    run: run.id,
    aggregation: aggregation.id,
    evaluation: evaluation?.id,
  }
}

async function main() {
  const ids = await discover()
  check('the seeded project, run and aggregation are reachable through the gateway', Boolean(ids))
  if (!ids) throw new Error('the development seed is missing')
  const review = `${BASE}/projects/${ids.project}/runs/${ids.run}/aggregations/${ids.aggregation}/review`
  const ws = await connect()
  await new Promise((resolve) => (ws.onopen = resolve))
  let last = 0
  const pending = new Map()
  const listeners = []
  ws.onmessage = ({ data }) => {
    const message = JSON.parse(data)
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id)
      pending.delete(message.id)
      if (message.error) reject(new Error(JSON.stringify(message.error)))
      else resolve(message.result)
    } else if (message.method) listeners.forEach((listener) => listener(message))
  }
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const id = ++last
      pending.set(id, { resolve, reject })
      ws.send(JSON.stringify({ id, method, params }))
    })
  const evaluate = async (expression) => {
    const r = await send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
    })
    if (r.exceptionDetails)
      throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text)
    return r.result.value
  }
  const waitFor = async (expression, what, ms = 15000) => {
    const end = Date.now() + ms
    while (Date.now() < end) {
      try {
        if (await evaluate(expression)) return
      } catch {
        /* the page is navigating */
      }
      await sleep(200)
    }
    // Leave evidence: what the page showed, and a screenshot, so a failure can be read afterwards.
    const shown = await evaluate(
      'location.href + "  " + document.body.innerText.slice(0, 300)',
    ).catch(() => '')
    await shot('timeout.png').catch(() => {})
    throw new Error(`timed out waiting for ${what}; the page showed: ${shown}`)
  }
  const go = async (url) => {
    await send('Page.navigate', { url })
    await sleep(500)
    await waitFor("document.readyState === 'complete'", 'the page to load')
  }
  const shot = async (name) => {
    const { data } = await send('Page.captureScreenshot', { format: 'png' })
    fs.writeFileSync(path.join(OUT, name), Buffer.from(data, 'base64'))
  }
  const key = async (name, code) => {
    const text = name === 'Enter' ? String.fromCharCode(13) : name
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: name, code, text })
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: name, code })
  }

  await send('Network.enable')
  await send('Page.enable')
  await send('Runtime.enable')
  await send('Log.enable')
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  })
  const problems = []
  listeners.push((m) => {
    // Name the request behind a failed load, so the console line "422" can be traced.
    if (
      m.method === 'Network.responseReceived' &&
      m.params.response.status >= 400 &&
      m.params.response.status !== 401
    ) {
      problems.push(`${m.params.response.status} ${m.params.response.url.replace(BASE, '')}`)
    }
    if (m.method === 'Runtime.exceptionThrown') problems.push(m.params.exceptionDetails.text)
    // Before signing in, /me and the session check answer 401 by design.
    if (
      m.method === 'Log.entryAdded' &&
      m.params.entry.level === 'error' &&
      !/401|Failed to load resource/.test(m.params.entry.text)
    ) {
      problems.push(m.params.entry.text)
    }
  })

  // 1. A deep link without a session goes to the sign-in page and remembers where it was going.
  await go(review)
  await waitFor("location.pathname === '/login'", 'the redirect to /login')
  check(
    'a deep link without a session redirects to /login',
    (await evaluate('location.search')).includes('redirect'),
  )

  // 2. Sign in through the real form.
  await waitFor(
    "document.querySelector('form') && document.querySelectorAll('input').length >= 2",
    'the sign-in form',
  )
  await evaluate(`(() => {
    const set = (el, v) => { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })) }
    const inputs = [...document.querySelectorAll('input')]
    set(inputs.find((i) => i.type !== 'password'), ${JSON.stringify(USER)})
    set(inputs.find((i) => i.type === 'password'), ${JSON.stringify(PASSWORD)})
    document.querySelector('form').requestSubmit()
  })()`)
  await waitFor("location.pathname !== '/login'", 'signing in to finish')
  const cookies = (await send('Network.getCookies', { urls: [BASE] })).cookies
  check(
    'the session cookie is HttpOnly and Secure, the CSRF cookie is readable by the client',
    cookies.some((c) => c.name === 'session' && c.httpOnly && c.secure) &&
      cookies.some((c) => c.name === 'csrf_token' && !c.httpOnly),
  )

  // 3. The review deep link, and a decision by keyboard. Signing in returned here already.
  await go(review)
  await waitFor(
    "document.querySelector('.detail-table') && document.querySelector('.row')",
    'the review screen',
  )
  check(
    'the review deep link shows the queue, its counts and the first person',
    (await evaluate("document.querySelectorAll('.queue-count').length")) === 3,
  )
  const revision = () =>
    evaluate(
      "Number(document.querySelector('.detail-revision')?.textContent.match(/\\d+/)?.[0] ?? -1)",
    )
  const before = await revision()
  await shot('review-light.png')
  await evaluate('document.activeElement.blur()')
  await key('2', 'Digit2')
  await waitFor(
    "document.querySelector('#decision-correct-female')?.checked",
    'key 2 to choose the label',
  )
  check(
    'key 2 chooses the second label and moves focus to Save',
    (await evaluate('document.activeElement?.id')) === 'decision-save',
  )
  await key('Enter', 'Enter')
  await waitFor(
    "document.querySelector('.decision-saved')?.textContent.trim().length > 0",
    'the saved message',
  )
  await sleep(800)
  check(
    'Enter saves the decision, announces it, and the revision advances',
    (await revision()) === before + 1,
    `${before} to ${await revision()}`,
  )

  // 4. Other screens, and no horizontal overflow (a screen without padding or with a wide table breaks it).
  const screens = [
    [
      `${BASE}/projects/${ids.project}/snapshots/${ids.snapshot}/runs/${ids.run}`,
      '.execution',
      'run',
    ],
    [
      `${BASE}/projects/${ids.project}/runs/${ids.run}/aggregations/${ids.aggregation}`,
      '.aggregation-detail-hash',
      'aggregation',
    ],
    [
      `${BASE}/projects/${ids.project}/runs/${ids.run}/aggregations/${ids.aggregation}/people`,
      '.record',
      'people',
    ],
    ...(ids.evaluation
      ? [
          [
            `${BASE}/projects/${ids.project}/runs/${ids.run}/evaluations/${ids.evaluation}`,
            '#ensemble-heading',
            'evaluation',
          ],
        ]
      : []),
    [
      `${BASE}/projects/${ids.project}/runs/${ids.run}/exports`,
      '.export, .export-list-empty',
      'exports',
    ],
  ]
  for (const [url, marker, name] of screens) {
    await go(url)
    await waitFor(`document.querySelector(${JSON.stringify(marker)})`, `the ${name} screen`)
    const overflow = await evaluate(
      'document.documentElement.scrollWidth - document.documentElement.clientWidth',
    )
    check(
      `the ${name} screen loads and does not scroll sideways`,
      overflow <= 1,
      `overflow ${overflow}px`,
    )
  }
  await shot('evaluation-light.png')

  // 5. Dark theme, and a hard reload on a deep link with a live session.
  await go(`${review}?person=demo-4`)
  await evaluate("document.documentElement.dataset.theme = 'dark'")
  await waitFor("document.querySelector('.detail-table')", 'the review screen after a hard reload')
  check('a hard reload on a deep link keeps the session', true)
  await shot('review-dark.png')

  check(
    'no uncaught error or failed request reached the console',
    problems.length === 0,
    problems.join(' | ').slice(0, 200),
  )
  ws.close()
}

try {
  await main()
} catch (error) {
  check('the smoke test ran to the end', false, String(error).slice(0, 300))
} finally {
  chrome.kill()
  const failed = results.filter((ok) => !ok).length
  console.log(`\n${results.length - failed}/${results.length} checks passed; screenshots in ${OUT}`)
  process.exit(failed ? 1 : 0)
}
